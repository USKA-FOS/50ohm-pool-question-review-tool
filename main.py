import os
import base64
import json
import requests
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from starlette.middleware.sessions import SessionMiddleware
import difflib

# FIXME: Find a better way to deal with this
from toc_helper import toc
contents = toc()

# Load config from .env file (.env.example is provided)
from dotenv import load_dotenv
load_dotenv()
CLIENT_ID = os.getenv('GITHUB_CLIENT_ID')
CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET')
OWNER = os.getenv('GITHUB_OWNER')
REPO = os.getenv('GITHUB_REPO')
SCOPE = 'repo'

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv('SESSION_SECRET'))
app.mount('/static', StaticFiles(directory='static'), name='static')
templates = Jinja2Templates(directory='templates')

# custom Jinja filter to render word diffs
def render_diff(diff):
    out = []
    for part in diff:
        if part['type'] == 'equal':
            out.append(part['text'])
        elif part['type'] == 'insert':
            out.append(f'<span class="diff added">{part['text']}</span>')
        elif part['type'] == 'delete':
            out.append(f'<span class="diff removed">{part['text']}</span>')
    return ' '.join(out)
templates.env.filters['render_diff'] = render_diff

# Function to create word diffs of questions and answers (to be rendered by render_diff())
def word_diff(a, b):
    ret = {}

    for field in ('question', 'answer_a', 'answer_b', 'answer_c', 'answer_d'):
        if a[field] is None or b[field] is None:
            ret[field] = ''
            continue

        a_words = a[field].split()
        b_words = b[field].split()

        matcher = difflib.SequenceMatcher(None, a_words, b_words)
        diff_list = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                diff_list.append({
                    'type': 'equal',
                    'text': ' '.join(a_words[i1:i2]),
                })
            elif tag == 'delete':
                diff_list.append({
                    'type': 'delete',
                    'text': ' '.join(a_words[i1:i2]),
                })
            elif tag == 'insert':
                diff_list.append({
                    'type': 'insert',
                    'text': ' '.join(b_words[j1:j2]),
                })
            elif tag == 'replace':
                diff_list.append({
                    'type': 'delete',
                    'text': ' '.join(a_words[i1:i2]),
                })
                diff_list.append({
                    'type': 'insert',
                    'text': ' '.join(b_words[j1:j2]),
                })

        ret[field] = diff_list
    return ret


# Various helpers
def get_token(request: Request):
    return request.session.get('token')

def github_headers(token):
    return {
        'Accept': 'application/vnd.github+json',
        'Authorization': f'Bearer {token}'
    }

def b64decode(data):
    return base64.b64decode(data).decode('utf-8')

def b64encode(data):
    return base64.b64encode(data.encode('utf-8')).decode()

# FIXME: Catch 403 and 404 errors here
def fetch(ref, key, token):
    path = f'questions/{key}.json'
    r = requests.get(
        f'https://api.github.com/repos/{OWNER}/{REPO}/contents/{path}',
        params={'ref': ref},
        headers=github_headers(token),
    )
    d = r.json()
    json_str = b64decode(d['content'])
    parsed = json.loads(json_str)
    return {
        'sha': d['sha'],
        'json': parsed,
    }


@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    logged_in = bool(get_token(request))
    if logged_in:
        # We need this to understand which questions have been reviewed already
        # FIXME: This will break at some point -- implement pagination
        r = requests.get(
            f'https://api.github.com/repos/{OWNER}/{REPO}/compare/FR_orig_DeepL...WIP',
            headers=github_headers(get_token(request)),
        )
        for file in r.json()['files']:
            # We need to split the questions/ prefix and the .json suffix from the filename
            # FIXME: Use pathlib for this?
            contents.mark_reviewed(file['filename'].split('/')[-1].split('.')[0])

        # Rate limit info will be prinated to understand whether we are about to have troubles
        r = requests.get(
            f'https://api.github.com/rate_limit',
            headers=github_headers(get_token(request)),
        )
        limit_json = r.json()

        table_of_contents = contents.toc.children
    else:
        limit_json = None
        table_of_contents = None
        
    return templates.TemplateResponse(
        'index.html',
        {'request': request,
         'logged_in': logged_in,
         'toc': table_of_contents,
         'rate_limit_json': limit_json}
    )


@app.get('/login')
def login():
    url = (
        'https://github.com/login/oauth/authorize'
        f'?client_id={CLIENT_ID}&scope={SCOPE}'
    )
    return RedirectResponse(url)


@app.get('/auth/callback')
def auth_callback(code: str, request: Request):
    resp = requests.post(
        'https://github.com/login/oauth/access_token',
        headers={'Accept': 'application/json'},
        data={
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'code': code,
        },
    )
    token = resp.json().get('access_token')
    request.session['token'] = token

    # Store username
    user_resp = requests.get('https://api.github.com/user', headers=github_headers(token))
    request.session['username'] = user_resp.json().get('login', 'unknown-user')
    return RedirectResponse('/')


@app.get('/logout')
def logout(request: Request):
    request.session.clear()
    return RedirectResponse('/')

# Extract GET parameter (used in forms) and redirect
@app.get('/edit', response_class=HTMLResponse)
def edit_question_redirect(request: Request):
    return edit_question(request, request.query_params['key'])

@app.get('/edit/{key}', response_class=HTMLResponse)
def edit_question(request: Request, key: str):
    token = get_token(request)
    if not token:
        return RedirectResponse('/login')

    data_de      = fetch('german_orig', key, token)
    data_fr_orig = fetch('FR_orig_DeepL', key, token)
    data_fr_wip  = fetch('WIP', key, token)

    return templates.TemplateResponse(
        'editor.html',
        {
            'request': request,
            'key': key,
            'de': data_de['json'],
            'fr': data_fr_wip['json'],
            'diff': word_diff(data_fr_orig['json'], data_fr_wip['json']),
            'sha': data_fr_wip['sha'],
            'next_question': contents.next_q_in_subsection(key),
            'prev_question': contents.prev_q_in_subsection(key),
            'next_section': contents.next_q_in_section(key),
            'prev_section': contents.prev_q_in_section(key)
        },
    )


@app.post('/save/{key}')
def save_question(
    request: Request,
    key: str,
    sha: str = Form(...),
    question: str = Form(...),
    answer_a: str = Form(...),
    answer_b: str = Form(...),
    answer_c: str = Form(...),
    answer_d: str = Form(...)
):
    token = get_token(request)
    if not token:
        return RedirectResponse('/login')

    # Prepare updated JSON
    data_fr_wip_json = fetch('WIP', key, token)['json']
    if data_fr_wip_json['question'] is not None: data_fr_wip_json['question'] = question
    if data_fr_wip_json['answer_a'] is not None: data_fr_wip_json['answer_a'] = answer_a
    if data_fr_wip_json['answer_b'] is not None: data_fr_wip_json['answer_b'] = answer_b
    if data_fr_wip_json['answer_c'] is not None: data_fr_wip_json['answer_c'] = answer_c
    if data_fr_wip_json['answer_d'] is not None: data_fr_wip_json['answer_d'] = answer_d
    username = request.session['username']
    data_fr_wip_json['review'] = username
    encoded = b64encode(json.dumps(data_fr_wip_json, indent=4))

    # Commit
    path = f'questions/{key}.json'
    commit_message = f'Update {key} via web UI (edited by @{username})'

    r = requests.put(
        f'https://api.github.com/repos/{OWNER}/{REPO}/contents/{path}',
        headers=github_headers(token),
        json={
            'message': commit_message,
            'content': encoded,
            'sha': sha,
            'branch': 'WIP',
        },
    )

    if r.status_code >= 300:
        return HTMLResponse(f'<h1>Error</h1><pre>{r.text}</pre>')

    return RedirectResponse(f'/edit/{key}', status_code=303)
