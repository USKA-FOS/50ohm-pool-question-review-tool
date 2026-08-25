import os
import base64
import json
import secrets
from urllib.parse import urlencode
import requests
from fastapi import FastAPI, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from typing import Optional

from starlette.middleware.sessions import SessionMiddleware
import difflib

# FIXME: Find a better way to deal with this
from toc_helper import toc

# Load config from .env file (.env.example is provided)
from dotenv import load_dotenv
load_dotenv()
CLIENT_ID = os.getenv('GITHUB_CLIENT_ID')
CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET')
OWNER = os.getenv('GITHUB_OWNER')
REPO = os.getenv('GITHUB_REPO')
CAMPAIGN_BRANCH = os.getenv('CAMPAIGN_BRANCH')
CALLBACK_URL = os.getenv('GITHUB_CALLBACK_URL')
SESSION_SECRET = os.getenv('SESSION_SECRET')
SCOPE = 'repo'
LANGUAGE_LABELS = {
    'de': 'German',
    'fr': 'French',
    'it': 'Italian',
}
REVIEW_STATUSES = ('to_be_reviewed', 'approved', 'rejected')
REVIEW_STATUS_LABELS = {
    'to_be_reviewed': 'To be reviewed',
    'approved': 'Approve',
    'rejected': 'Reject',
}

required_config = {
    'GITHUB_CLIENT_ID': CLIENT_ID,
    'GITHUB_CLIENT_SECRET': CLIENT_SECRET,
    'GITHUB_OWNER': OWNER,
    'GITHUB_REPO': REPO,
    'CAMPAIGN_BRANCH': CAMPAIGN_BRANCH,
    'GITHUB_CALLBACK_URL': CALLBACK_URL,
    'SESSION_SECRET': SESSION_SECRET,
}
missing_config = [key for key, value in required_config.items() if not value]
if missing_config:
    raise RuntimeError(f"Missing required configuration: {', '.join(missing_config)}")

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=os.getenv('SESSION_HTTPS_ONLY', 'true').lower() == 'true',
    same_site='lax',
)
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


def fetch_path(ref, path, token):
    r = requests.get(
        f'https://api.github.com/repos/{OWNER}/{REPO}/contents/{path}',
        params={'ref': ref},
        headers=github_headers(token),
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    json_str = b64decode(d['content'])
    parsed = json.loads(json_str)
    return {
        'sha': d['sha'],
        'json': parsed,
    }


def update_path(path, payload, sha, message, token):
    encoded = b64encode(json.dumps(payload, ensure_ascii=True, indent=2) + '\n')
    request_payload = {
        'message': message,
        'content': encoded,
        'branch': CAMPAIGN_BRANCH,
    }
    if sha is not None:
        request_payload['sha'] = sha
    response = requests.put(
        f'https://api.github.com/repos/{OWNER}/{REPO}/contents/{path}',
        headers=github_headers(token),
        json=request_payload,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def fetch_optional_path(ref, path, token):
    try:
        return fetch_path(ref, path, token)
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise


def github_commits_for_path(path, token):
    response = requests.get(
        f'https://api.github.com/repos/{OWNER}/{REPO}/commits',
        params={'sha': CAMPAIGN_BRANCH, 'path': path, 'per_page': 100},
        headers=github_headers(token),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def commit_author(commit):
    github_author = commit.get('author')
    if isinstance(github_author, dict) and github_author.get('login'):
        return github_author['login']
    commit_author_data = commit.get('commit', {}).get('author', {})
    return commit_author_data.get('name') or 'unknown'


def status_author(path, language, token):
    for commit in github_commits_for_path(path, token):
        current = fetch_optional_path(commit['sha'], path, token)
        if current is None:
            continue
        current_status = current['json'].get('review', {}).get(language)
        parents = commit.get('parents', [])
        previous_status = None
        if parents:
            previous = fetch_optional_path(parents[0]['sha'], path, token)
            if previous is not None:
                previous_status = previous['json'].get('review', {}).get(language)
        if current_status != previous_status:
            return commit_author(commit)
    return 'unknown'


def load_comments(question_id, language, token):
    path = f'reviews/{question_id}.json'
    current = fetch_optional_path(CAMPAIGN_BRANCH, path, token)
    if current is None:
        return None, []
    payload = current['json']
    if payload.get('schema_version') != 1 or payload.get('question_id') != question_id:
        raise ValueError('Invalid campaign comment file.')
    comments_by_language = payload.get('comments')
    if not isinstance(comments_by_language, dict):
        raise ValueError('Invalid campaign comments object.')
    comments = comments_by_language.get(language, [])
    if not isinstance(comments, list) or any(not isinstance(comment, str) for comment in comments):
        raise ValueError(f'Invalid campaign comments for {language}.')

    authors = ['unknown'] * len(comments)
    previous_count = 0
    for commit in reversed(github_commits_for_path(path, token)):
        version = fetch_optional_path(commit['sha'], path, token)
        if version is None:
            continue
        version_comments = version['json'].get('comments', {}).get(language, [])
        if not isinstance(version_comments, list):
            continue
        for index in range(previous_count, min(len(version_comments), len(authors))):
            authors[index] = commit_author(commit)
        previous_count = max(previous_count, len(version_comments))
    return current['sha'], [
        {'text': text, 'author': authors[index]}
        for index, text in enumerate(comments)
    ]


def canonical_to_legacy_question(payload):
    return {
        'question': payload['question'],
        'answer_a': payload['answer_a'],
        'answer_b': payload['answer_b'],
        'answer_c': payload['answer_c'],
        'answer_d': payload['answer_d'],
        'picture_question': payload['picture_question_url'],
        'picture_a': payload['picture_answer_a_url'],
        'picture_b': payload['picture_answer_b_url'],
        'picture_c': payload['picture_answer_c_url'],
        'picture_d': payload['picture_answer_d_url'],
    }


def meta_with_status(meta, question_id, language, status):
    if status not in REVIEW_STATUSES:
        raise ValueError(f'Unsupported review status: {status}.')
    if meta.get('id') != question_id:
        raise ValueError('Question metadata id does not match its directory.')
    review = meta.get('review')
    if not isinstance(review, dict) or language not in review:
        raise ValueError(f'Question metadata has no review status for {language}.')
    result = dict(meta)
    result['review'] = dict(review)
    result['review'][language] = status
    return result


def edit_url(key, reference_language, review_language):
    query = urlencode({
        'reference_language': reference_language,
        'review_language': review_language,
    })
    return f'/edit/{key}?{query}'


def select_languages(manifest, requested_reference=None, requested_review=None):
    languages = manifest.get('languages', [])
    editable_languages = manifest.get('editable_languages', [])
    if len(languages) < 2:
        raise ValueError('A review campaign requires at least two languages.')
    if not editable_languages or any(language not in languages for language in editable_languages):
        raise ValueError('Campaign editable_languages must be a non-empty subset of languages.')

    review_language = requested_review or ('fr' if 'fr' in editable_languages else editable_languages[0])
    if review_language not in editable_languages:
        raise ValueError(f'Language {review_language} is not editable in this campaign.')

    reference_choices = [language for language in languages if language != review_language]
    reference_language = requested_reference or ('de' if 'de' in reference_choices else reference_choices[0])
    if reference_language not in reference_choices:
        raise ValueError('Reference and review languages must be distinct campaign languages.')
    return reference_language, review_language


def load_campaign(token, requested_reference=None, requested_review=None):
    manifest = fetch_path(CAMPAIGN_BRANCH, 'campaign.meta.json', token)['json']
    if manifest.get('campaign_branch') != CAMPAIGN_BRANCH:
        raise ValueError('Configured branch does not match campaign.meta.json.')
    reference_language, review_language = select_languages(
        manifest,
        requested_reference,
        requested_review,
    )
    navigation = fetch_path(
        CAMPAIGN_BRANCH,
        f'derived/question_pool_ch-{reference_language}.json',
        token,
    )['json']
    campaign_toc = toc(navigation)
    navigation_index = fetch_path(
        CAMPAIGN_BRANCH,
        'derived/navigation.index.json',
        token,
    )['json']
    questions_by_number = {}
    for item in navigation_index['items']:
        question_id = item['question_id']
        number = item['internal_code']
        questions_by_number[number] = {
            'question_id': question_id,
            'review': item['review'],
        }
        if item.get('review', {}).get(review_language) == 'approved':
            campaign_toc.mark_reviewed(number)
    return manifest, campaign_toc, questions_by_number, reference_language, review_language


@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    logged_in = bool(get_token(request))
    if logged_in:
        try:
            manifest, campaign_toc, _, reference_language, review_language = load_campaign(
                get_token(request),
                request.query_params.get('reference_language'),
                request.query_params.get('review_language'),
            )
            r = requests.get(
                f'https://api.github.com/rate_limit',
                headers=github_headers(get_token(request)),
            )
            r.raise_for_status()
            limit_json = r.json()
        except requests.exceptions.HTTPError as e:
            return HTMLResponse(f'<h1>Error</h1><pre>{e.args[0]}</pre>')
        except ValueError as e:
            return HTMLResponse(f'<h1>Invalid language selection</h1><pre>{e}</pre>', status_code=400)

        table_of_contents = campaign_toc.toc.children
        languages = manifest['languages']
        editable_languages = manifest['editable_languages']
    else:
        limit_json = None
        table_of_contents = None
        languages = []
        editable_languages = []
        reference_language = None
        review_language = None
        
    return templates.TemplateResponse(
        request=request,
        name='index.html',
        context={
            'logged_in': logged_in,
            'toc': table_of_contents,
            'rate_limit_json': limit_json,
            'languages': languages,
            'editable_languages': editable_languages,
            'reference_language': reference_language,
            'review_language': review_language,
            'language_labels': LANGUAGE_LABELS,
        },
    )


@app.get('/healthz')
def healthz():
    return {'status': 'ok'}


@app.get('/login')
def login(request: Request):
    state = secrets.token_urlsafe(32)
    request.session['oauth_state'] = state
    query = urlencode({
        'client_id': CLIENT_ID,
        'redirect_uri': CALLBACK_URL,
        'scope': SCOPE,
        'state': state,
    })
    return RedirectResponse(f'https://github.com/login/oauth/authorize?{query}')


@app.get('/auth/callback')
def auth_callback(code: str, state: str, request: Request):
    expected_state = request.session.pop('oauth_state', None)
    if not expected_state or not secrets.compare_digest(state, expected_state):
        return HTMLResponse('<h1>Invalid OAuth state</h1>', status_code=400)

    resp = requests.post(
        'https://github.com/login/oauth/access_token',
        headers={'Accept': 'application/json'},
        data={
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'code': code,
            'redirect_uri': CALLBACK_URL,
        },
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json().get('access_token')
    if not token:
        return HTMLResponse('<h1>GitHub authentication failed</h1>', status_code=401)
    request.session['token'] = token

    # Store username
    user_resp = requests.get(
        'https://api.github.com/user',
        headers=github_headers(token),
        timeout=15,
    )
    user_resp.raise_for_status()
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

    try:
        _, campaign_toc, questions_by_number, reference_language, review_language = load_campaign(
            token,
            request.query_params.get('reference_language'),
            request.query_params.get('review_language'),
        )
        if key not in questions_by_number:
            return HTMLResponse('<h1>Question not found in campaign</h1>', status_code=404)
        question_id = questions_by_number[key]['question_id']
        data_reference = fetch_path(
            CAMPAIGN_BRANCH,
            f'pool/questions/{question_id}/question.{reference_language}.json',
            token,
        )
        data_review = fetch_path(
            CAMPAIGN_BRANCH,
            f'pool/questions/{question_id}/question.{review_language}.json',
            token,
        )
        data_meta = fetch_path(
            CAMPAIGN_BRANCH,
            f'pool/questions/{question_id}/question.meta.json',
            token,
        )
        reference = canonical_to_legacy_question(data_reference['json'])
        review = canonical_to_legacy_question(data_review['json'])
        review_status = data_meta['json'].get('review', {}).get(review_language)
        meta_path = f'pool/questions/{question_id}/question.meta.json'
        review_status_author = status_author(meta_path, review_language, token)
        comments_sha, comments = load_comments(question_id, review_language, token)
    except (requests.exceptions.HTTPError, ValueError) as e:
        return HTMLResponse(f'<h1>Error</h1><pre>{e.args[0]}</pre>')

    return templates.TemplateResponse(
        request=request,
        name='editor.html',
        context={
            'key': key,
            'reference': reference,
            'review': review,
            'diff': word_diff(review, review),
            'sha': data_review['sha'],
            'meta_sha': data_meta['sha'],
            'review_status': review_status,
            'review_status_author': review_status_author,
            'review_statuses': REVIEW_STATUSES,
            'review_status_labels': REVIEW_STATUS_LABELS,
            'comments_sha': comments_sha or '',
            'comments': comments,
            'reference_language': reference_language,
            'review_language': review_language,
            'reference_language_label': LANGUAGE_LABELS.get(reference_language, reference_language.upper()),
            'review_language_label': LANGUAGE_LABELS.get(review_language, review_language.upper()),
            'next_question': campaign_toc.next_q_in_subsection(key),
            'prev_question': campaign_toc.prev_q_in_subsection(key),
            'next_section': campaign_toc.next_q_in_section(key),
            'prev_section': campaign_toc.prev_q_in_section(key)
        },
    )


@app.post('/save/{key}')
def save_question(
    request: Request,
    key: str,
    sha: str = Form(...),
    question: str = Form(...),
    answer_a: Optional[str] = Form(None),
    answer_b: Optional[str] = Form(None),
    answer_c: Optional[str] = Form(None),
    answer_d: Optional[str] = Form(None),
    comment: Optional[str] = Form(None)
):
    return HTMLResponse(
        '<h1>Text editing not enabled</h1><p>No question text was written.</p>',
        status_code=405,
    )


@app.post('/status/{key}')
def update_review_status(
    request: Request,
    key: str,
    meta_sha: str = Form(...),
    status: str = Form(...),
):
    token = get_token(request)
    if not token:
        return RedirectResponse('/login')

    reference_language = request.query_params.get('reference_language')
    review_language = request.query_params.get('review_language')
    try:
        _, _, questions_by_number, reference_language, review_language = load_campaign(
            token,
            reference_language,
            review_language,
        )
        if key not in questions_by_number:
            return HTMLResponse('<h1>Question not found in campaign</h1>', status_code=404)
        question_id = questions_by_number[key]['question_id']
        meta_path = f'pool/questions/{question_id}/question.meta.json'
        current_meta = fetch_path(CAMPAIGN_BRANCH, meta_path, token)
        if current_meta['sha'] != meta_sha:
            return HTMLResponse(
                '<h1>Concurrent change detected</h1><p>Reload the question before changing its status.</p>',
                status_code=409,
            )
        updated_meta = meta_with_status(current_meta['json'], question_id, review_language, status)
        if updated_meta != current_meta['json']:
            update_path(
                meta_path,
                updated_meta,
                current_meta['sha'],
                f'Set {key} {review_language} review status to {status}',
                token,
            )
    except ValueError as exc:
        return HTMLResponse(f'<h1>Invalid campaign data</h1><pre>{exc}</pre>', status_code=400)
    except requests.exceptions.HTTPError as exc:
        status_code = 409 if exc.response is not None and exc.response.status_code in (409, 422) else 502
        return HTMLResponse(f'<h1>GitHub write failed</h1><pre>{exc}</pre>', status_code=status_code)

    return RedirectResponse(edit_url(key, reference_language, review_language), status_code=303)


@app.post('/comment/{key}')
def add_review_comment(
    request: Request,
    key: str,
    comments_sha: str = Form(''),
    comment: str = Form(...),
):
    token = get_token(request)
    if not token:
        return RedirectResponse('/login')
    reference_language = request.query_params.get('reference_language')
    review_language = request.query_params.get('review_language')
    try:
        _, _, questions_by_number, reference_language, review_language = load_campaign(
            token,
            reference_language,
            review_language,
        )
        if key not in questions_by_number:
            return HTMLResponse('<h1>Question not found in campaign</h1>', status_code=404)
        text = comment.strip()
        if not text:
            return HTMLResponse('<h1>Empty comment</h1>', status_code=400)
        question_id = questions_by_number[key]['question_id']
        path = f'reviews/{question_id}.json'
        current = fetch_optional_path(CAMPAIGN_BRANCH, path, token)
        current_sha = current['sha'] if current is not None else ''
        if current_sha != comments_sha:
            return HTMLResponse(
                '<h1>Concurrent change detected</h1><p>Reload the question before adding the comment.</p>',
                status_code=409,
            )
        if current is None:
            payload = {
                'schema_version': 1,
                'question_id': question_id,
                'comments': {},
            }
        else:
            payload = current['json']
            if payload.get('schema_version') != 1 or payload.get('question_id') != question_id:
                raise ValueError('Invalid campaign comment file.')
            payload = dict(payload)
            payload['comments'] = dict(payload.get('comments', {}))
        language_comments = payload['comments'].get(review_language, [])
        if not isinstance(language_comments, list) or any(not isinstance(item, str) for item in language_comments):
            raise ValueError(f'Invalid campaign comments for {review_language}.')
        payload['comments'][review_language] = [*language_comments, text]
        update_path(
            path,
            payload,
            current['sha'] if current is not None else None,
            f'Comment on {key} {review_language} review',
            token,
        )
    except ValueError as exc:
        return HTMLResponse(f'<h1>Invalid campaign data</h1><pre>{exc}</pre>', status_code=400)
    except requests.exceptions.HTTPError as exc:
        status_code = 409 if exc.response is not None and exc.response.status_code in (409, 422) else 502
        return HTMLResponse(f'<h1>GitHub write failed</h1><pre>{exc}</pre>', status_code=status_code)
    return RedirectResponse(edit_url(key, reference_language, review_language), status_code=303)
