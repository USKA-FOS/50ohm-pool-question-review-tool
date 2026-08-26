import os
import base64
from collections import defaultdict
from contextvars import ContextVar
import hashlib
from io import BytesIO
import json
import logging
import secrets
import tarfile
import threading
import time
from urllib.parse import quote, urlencode
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
GITHUB_PROFILE = os.getenv('GITHUB_PROFILE', 'false').lower() == 'true'
CAMPAIGN_REFRESH_SECONDS = max(float(os.getenv('CAMPAIGN_REFRESH_SECONDS', '30')), 0.0)
SCOPE = 'repo'
LANGUAGE_LABELS = {
    'de': 'German',
    'fr': 'French',
    'it': 'Italian',
}
REVIEW_STATUSES = ('to_be_reviewed', 'approved')
PREFERENCE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
REFERENCE_LANGUAGE_COOKIE = '50ohm_reference_language'
REVIEW_LANGUAGE_COOKIE = '50ohm_review_language'
LAST_QUESTION_COOKIE = '50ohm_last_question'
PROFILE_REQUEST_ID = ContextVar('profile_request_id', default='-')
PROFILE_EVENTS = ContextVar('profile_events', default=None)
LOGGER = logging.getLogger('uvicorn.error')
CAMPAIGN_SNAPSHOT = None
CAMPAIGN_SNAPSHOT_LOCK = threading.Lock()
STATUS_AUTHOR_CACHE = {}
COMMENT_AUTHOR_CACHE = {}

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


def record_github_profile(operation, resource, duration_ms, status):
    event = {
        'operation': operation,
        'resource': resource,
        'duration_ms': duration_ms,
        'status': status,
    }
    events = PROFILE_EVENTS.get()
    if events is not None:
        events.append(event)
    return event


def github_request(method, url, operation, resource='', **kwargs):
    started = time.perf_counter()
    try:
        response = requests.request(method, url, **kwargs)
    except requests.exceptions.RequestException as exc:
        duration_ms = (time.perf_counter() - started) * 1000
        if GITHUB_PROFILE:
            record_github_profile(operation, resource, duration_ms, 'error')
            LOGGER.info(
                '[github_profile] request_id=%s method=%s operation=%s resource=%s '
                'status=error duration_ms=%.1f error=%s',
                PROFILE_REQUEST_ID.get(),
                method,
                operation,
                resource or '-',
                duration_ms,
                type(exc).__name__,
            )
        raise

    duration_ms = (time.perf_counter() - started) * 1000
    if GITHUB_PROFILE:
        record_github_profile(operation, resource, duration_ms, response.status_code)
        LOGGER.info(
            '[github_profile] request_id=%s method=%s operation=%s resource=%s '
            'status=%s duration_ms=%.1f github_request_id=%s rate_remaining=%s',
            PROFILE_REQUEST_ID.get(),
            method,
            operation,
            resource or '-',
            response.status_code,
            duration_ms,
            response.headers.get('x-github-request-id', '-'),
            response.headers.get('x-ratelimit-remaining', '-'),
        )
    return response


@app.middleware('http')
async def profile_http_request(request: Request, call_next):
    if not GITHUB_PROFILE:
        return await call_next(request)

    request_id_token = PROFILE_REQUEST_ID.set(secrets.token_hex(4))
    events_token = PROFILE_EVENTS.set([])
    started = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        duration_ms = (time.perf_counter() - started) * 1000
        events = PROFILE_EVENTS.get() or []
        github_ms = sum(event['duration_ms'] for event in events)
        grouped = defaultdict(lambda: {'count': 0, 'duration_ms': 0.0})
        for event in events:
            grouped[event['operation']]['count'] += 1
            grouped[event['operation']]['duration_ms'] += event['duration_ms']
        breakdown = ','.join(
            f'{operation}:{values["count"]}/{values["duration_ms"]:.1f}ms'
            for operation, values in sorted(grouped.items())
        ) or '-'
        status = response.status_code if response is not None else 500
        LOGGER.info(
            '[request_profile] request_id=%s method=%s path=%s status=%s '
            'duration_ms=%.1f github_calls=%s github_ms=%.1f breakdown=%s',
            PROFILE_REQUEST_ID.get(),
            request.method,
            request.url.path,
            status,
            duration_ms,
            len(events),
            github_ms,
            breakdown,
        )
        if response is not None:
            response.headers['Server-Timing'] = f'app;dur={duration_ms:.1f}, github;dur={github_ms:.1f}'
        PROFILE_EVENTS.reset(events_token)
        PROFILE_REQUEST_ID.reset(request_id_token)

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


def fetch_repository_path(repository, ref, path, token):
    repository_parts = repository.split('/')
    if len(repository_parts) != 2 or not all(repository_parts):
        raise ValueError(f'Invalid GitHub repository name: {repository}.')
    r = github_request(
        'GET',
        f'https://api.github.com/repos/{repository}/contents/{path}',
        operation='contents.read',
        resource=f'{repository}:{path}',
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


def oldest_campaign_commit_for_path(path, token):
    response = github_request(
        'GET',
        f'https://api.github.com/repos/{OWNER}/{REPO}/commits',
        operation='commits.oldest',
        resource=path,
        params={'sha': CAMPAIGN_BRANCH, 'path': path, 'per_page': 1},
        headers=github_headers(token),
        timeout=15,
    )
    response.raise_for_status()
    last_url = response.links.get('last', {}).get('url')
    if last_url:
        if not last_url.startswith('https://api.github.com/'):
            raise ValueError('GitHub returned an invalid commit pagination URL.')
        response = github_request(
            'GET',
            last_url,
            operation='commits.oldest',
            resource=path,
            headers=github_headers(token),
            timeout=15,
        )
        response.raise_for_status()
    commits = response.json()
    if not isinstance(commits, list) or len(commits) != 1 or not commits[0].get('sha'):
        raise ValueError(f'Cannot resolve the original campaign commit for {path}.')
    return commits[0]['sha']


def git_blob_sha(raw):
    header = f'blob {len(raw)}\0'.encode('ascii')
    return hashlib.sha1(header + raw).hexdigest()


def campaign_branch_head(token):
    ref = quote(f'heads/{CAMPAIGN_BRANCH}', safe='/')
    response = github_request(
        'GET',
        f'https://api.github.com/repos/{OWNER}/{REPO}/git/ref/{ref}',
        operation='branch.read',
        resource=CAMPAIGN_BRANCH,
        headers=github_headers(token),
        timeout=15,
    )
    response.raise_for_status()
    sha = response.json().get('object', {}).get('sha')
    if not sha:
        raise ValueError(f'Cannot resolve campaign branch head: {CAMPAIGN_BRANCH}.')
    return sha


def download_campaign_snapshot(ref, token):
    response = github_request(
        'GET',
        f'https://api.github.com/repos/{OWNER}/{REPO}/tarball/{quote(ref, safe="")}',
        operation='archive.read',
        resource=ref,
        headers=github_headers(token),
        timeout=60,
    )
    response.raise_for_status()
    files = {}
    with tarfile.open(fileobj=BytesIO(response.content), mode='r:gz') as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.endswith('.json'):
                continue
            _, separator, path = member.name.partition('/')
            if not separator:
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            raw = extracted.read()
            try:
                payload = json.loads(raw.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f'Invalid JSON in campaign archive: {path}.') from exc
            files[path] = {
                'sha': git_blob_sha(raw),
                'json': payload,
            }
    if 'campaign.meta.json' not in files:
        raise ValueError('Campaign archive has no campaign.meta.json.')
    return files


def invalidate_campaign_snapshot():
    global CAMPAIGN_SNAPSHOT
    with CAMPAIGN_SNAPSHOT_LOCK:
        CAMPAIGN_SNAPSHOT = None


def ensure_campaign_snapshot(token):
    global CAMPAIGN_SNAPSHOT
    now = time.monotonic()
    if (
        CAMPAIGN_SNAPSHOT is not None
        and now - CAMPAIGN_SNAPSHOT['checked_at'] < CAMPAIGN_REFRESH_SECONDS
    ):
        return CAMPAIGN_SNAPSHOT
    with CAMPAIGN_SNAPSHOT_LOCK:
        now = time.monotonic()
        if (
            CAMPAIGN_SNAPSHOT is not None
            and now - CAMPAIGN_SNAPSHOT['checked_at'] < CAMPAIGN_REFRESH_SECONDS
        ):
            return CAMPAIGN_SNAPSHOT
        head_sha = campaign_branch_head(token)
        if CAMPAIGN_SNAPSHOT is not None and CAMPAIGN_SNAPSHOT['head_sha'] == head_sha:
            CAMPAIGN_SNAPSHOT['checked_at'] = now
            return CAMPAIGN_SNAPSHOT
        if CAMPAIGN_SNAPSHOT is not None:
            CAMPAIGN_SNAPSHOT = {
                **CAMPAIGN_SNAPSHOT,
                'head_sha': head_sha,
                'current_files': download_campaign_snapshot(head_sha, token),
                'checked_at': now,
            }
            return CAMPAIGN_SNAPSHOT
        export_sha = oldest_campaign_commit_for_path('campaign.meta.json', token)
        current_files = download_campaign_snapshot(head_sha, token)
        original_files = download_campaign_snapshot(export_sha, token)
        CAMPAIGN_SNAPSHOT = {
            'head_sha': head_sha,
            'export_sha': export_sha,
            'current_files': current_files,
            'original_files': original_files,
            'checked_at': now,
        }
        return CAMPAIGN_SNAPSHOT


def fetch_path(ref, path, token):
    if ref == CAMPAIGN_BRANCH:
        snapshot = ensure_campaign_snapshot(token)
        try:
            return snapshot['current_files'][path]
        except KeyError as exc:
            raise ValueError(f'Campaign path does not exist: {path}.') from exc
    return fetch_repository_path(f'{OWNER}/{REPO}', ref, path, token)


def fetch_original_question(manifest, question_id, language, token):
    if question_id not in manifest.get('question_ids', []):
        raise ValueError(f'Question {question_id} is outside the campaign scope.')
    path = f'pool/questions/{question_id}/question.{language}.json'
    snapshot = ensure_campaign_snapshot(token)
    try:
        return snapshot['original_files'][path]
    except KeyError as exc:
        raise ValueError(f'Original campaign path does not exist: {path}.') from exc


class CampaignConflictError(RuntimeError):
    pass


class CampaignWriteError(RuntimeError):
    pass


def serialized_json(payload):
    return (json.dumps(payload, ensure_ascii=True, indent=2) + '\n').encode('utf-8')


def commit_campaign_files(changes, message, expected_head, token):
    if not changes:
        return expected_head
    additions = [
        {
            'path': path,
            'contents': base64.b64encode(serialized_json(payload)).decode('ascii'),
        }
        for path, payload in sorted(changes.items())
    ]
    mutation = '''
mutation CommitCampaignFiles($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) {
    commit { oid }
  }
}
'''
    response = github_request(
        'POST',
        'https://api.github.com/graphql',
        operation='commit.write',
        resource=f'{len(additions)} files',
        headers=github_headers(token),
        json={
            'query': mutation,
            'variables': {
                'input': {
                    'branch': {
                        'repositoryNameWithOwner': f'{OWNER}/{REPO}',
                        'branchName': CAMPAIGN_BRANCH,
                    },
                    'message': {'headline': message},
                    'expectedHeadOid': expected_head,
                    'fileChanges': {'additions': additions},
                }
            },
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    errors = payload.get('errors', [])
    if errors:
        error_message = '; '.join(str(error.get('message', 'unknown GraphQL error')) for error in errors)
        if 'expectedHeadOid' in error_message or 'head' in error_message.lower():
            invalidate_campaign_snapshot()
            raise CampaignConflictError(error_message)
        raise CampaignWriteError(error_message)
    commit_sha = payload.get('data', {}).get('createCommitOnBranch', {}).get('commit', {}).get('oid')
    if not commit_sha:
        raise CampaignWriteError('GitHub did not return the created commit oid.')

    global CAMPAIGN_SNAPSHOT
    with CAMPAIGN_SNAPSHOT_LOCK:
        if CAMPAIGN_SNAPSHOT is None or CAMPAIGN_SNAPSHOT['head_sha'] != expected_head:
            invalidate_after_lock = True
        else:
            invalidate_after_lock = False
            for path, content in changes.items():
                raw = serialized_json(content)
                CAMPAIGN_SNAPSHOT['current_files'][path] = {
                    'sha': git_blob_sha(raw),
                    'json': content,
                }
            CAMPAIGN_SNAPSHOT['head_sha'] = commit_sha
            CAMPAIGN_SNAPSHOT['checked_at'] = time.monotonic()
    if invalidate_after_lock:
        invalidate_campaign_snapshot()
    return commit_sha


def fetch_optional_path(ref, path, token):
    if ref == CAMPAIGN_BRANCH:
        return ensure_campaign_snapshot(token)['current_files'].get(path)
    try:
        return fetch_path(ref, path, token)
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise


def github_commits_for_path(path, token):
    response = github_request(
        'GET',
        f'https://api.github.com/repos/{OWNER}/{REPO}/commits',
        operation='commits.list',
        resource=path,
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
    current_file = fetch_path(CAMPAIGN_BRANCH, path, token)
    cache_key = (path, language, current_file['sha'])
    if cache_key in STATUS_AUTHOR_CACHE:
        return STATUS_AUTHOR_CACHE[cache_key]
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
            author = commit_author(commit)
            STATUS_AUTHOR_CACHE[cache_key] = author
            return author
    STATUS_AUTHOR_CACHE[cache_key] = 'unknown'
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

    cache_key = (path, language, current['sha'])
    if cache_key in COMMENT_AUTHOR_CACHE:
        authors = COMMENT_AUTHOR_CACHE[cache_key]
        return current['sha'], [
            {'text': text, 'author': authors[index]}
            for index, text in enumerate(comments)
        ]

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
    COMMENT_AUTHOR_CACHE[cache_key] = authors
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


def content_with_edits(content, question_id, language, values):
    if content.get('question_id') != question_id:
        raise ValueError('Question content id does not match its directory.')
    if content.get('language') != language:
        raise ValueError('Question content language does not match the active review language.')

    result = dict(content)
    for field in ('question', 'answer_a', 'answer_b', 'answer_c', 'answer_d'):
        current_value = content.get(field)
        submitted_value = values.get(field)
        if current_value is None:
            if submitted_value is not None:
                raise ValueError(f'Nullable field {field} cannot be created by the editor.')
            result[field] = None
        elif submitted_value is None:
            raise ValueError(f'Missing editable field: {field}.')
        else:
            result[field] = submitted_value

    if not result['question'].strip():
        raise ValueError('Question text cannot be empty.')
    return result


def comment_with_append(current, question_id, language, text):
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

    language_comments = payload['comments'].get(language, [])
    if not isinstance(language_comments, list) or any(not isinstance(item, str) for item in language_comments):
        raise ValueError(f'Invalid campaign comments for {language}.')
    payload['comments'][language] = [*language_comments, text]
    return payload


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

    reference_language = requested_reference or ('de' if 'de' in languages else languages[0])
    if reference_language not in languages:
        raise ValueError(f'Language {reference_language} is not available in this campaign.')
    return reference_language, review_language


def load_campaign(token, requested_reference=None, requested_review=None, manifest=None):
    if manifest is None:
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


def requested_languages(request, manifest):
    requested_reference = request.query_params.get('reference_language')
    if requested_reference is None:
        remembered_reference = request.cookies.get(REFERENCE_LANGUAGE_COOKIE)
        if remembered_reference in manifest.get('languages', []):
            requested_reference = remembered_reference

    requested_review = request.query_params.get('review_language')
    if requested_review is None:
        remembered_review = request.cookies.get(REVIEW_LANGUAGE_COOKIE)
        if remembered_review in manifest.get('editable_languages', []):
            requested_review = remembered_review
    return requested_reference, requested_review


def remember_review_preferences(response, reference_language, review_language, last_question=None):
    cookie_options = {
        'max_age': PREFERENCE_COOKIE_MAX_AGE,
        'httponly': True,
        'samesite': 'lax',
        'secure': os.getenv('SESSION_HTTPS_ONLY', 'true').lower() == 'true',
    }
    response.set_cookie(REFERENCE_LANGUAGE_COOKIE, reference_language, **cookie_options)
    response.set_cookie(REVIEW_LANGUAGE_COOKIE, review_language, **cookie_options)
    if last_question is not None:
        response.set_cookie(LAST_QUESTION_COOKIE, last_question, **cookie_options)


@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    logged_in = bool(get_token(request))
    if logged_in:
        try:
            manifest = fetch_path(CAMPAIGN_BRANCH, 'campaign.meta.json', get_token(request))['json']
            requested_reference, requested_review = requested_languages(request, manifest)
            manifest, campaign_toc, questions_by_number, reference_language, review_language = load_campaign(
                get_token(request),
                requested_reference,
                requested_review,
                manifest,
            )
            limit_json = None
        except requests.exceptions.HTTPError as e:
            return HTMLResponse(f'<h1>Error</h1><pre>{e.args[0]}</pre>')
        except ValueError as e:
            return HTMLResponse(f'<h1>Invalid language selection</h1><pre>{e}</pre>', status_code=400)

        table_of_contents = campaign_toc.toc.children
        languages = manifest['languages']
        editable_languages = manifest['editable_languages']
        remembered_question = request.cookies.get(LAST_QUESTION_COOKIE, '')
        if remembered_question not in questions_by_number:
            remembered_question = ''
    else:
        limit_json = None
        table_of_contents = None
        languages = []
        editable_languages = []
        reference_language = None
        review_language = None
        remembered_question = ''
        
    response = templates.TemplateResponse(
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
            'remembered_question': remembered_question,
            'language_labels': LANGUAGE_LABELS,
        },
    )
    if logged_in:
        remember_review_preferences(response, reference_language, review_language)
    return response


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

    resp = github_request(
        'POST',
        'https://github.com/login/oauth/access_token',
        operation='oauth.token',
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
    user_resp = github_request(
        'GET',
        'https://api.github.com/user',
        operation='oauth.user',
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
        manifest = fetch_path(CAMPAIGN_BRANCH, 'campaign.meta.json', token)['json']
        requested_reference, requested_review = requested_languages(request, manifest)
        manifest, campaign_toc, questions_by_number, reference_language, review_language = load_campaign(
            token,
            requested_reference,
            requested_review,
            manifest,
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
        data_original = fetch_original_question(manifest, question_id, review_language, token)
        data_meta = fetch_path(
            CAMPAIGN_BRANCH,
            f'pool/questions/{question_id}/question.meta.json',
            token,
        )
        reference = canonical_to_legacy_question(data_reference['json'])
        review = canonical_to_legacy_question(data_review['json'])
        original = canonical_to_legacy_question(data_original['json'])
        review_status = data_meta['json'].get('review', {}).get(review_language)
        meta_path = f'pool/questions/{question_id}/question.meta.json'
        review_status_author = status_author(meta_path, review_language, token)
        comments_sha, comments = load_comments(question_id, review_language, token)
    except (requests.exceptions.HTTPError, ValueError) as e:
        return HTMLResponse(f'<h1>Error</h1><pre>{e.args[0]}</pre>')

    response = templates.TemplateResponse(
        request=request,
        name='editor.html',
        context={
            'key': key,
            'reference': reference,
            'review': review,
            'diff': word_diff(original, review),
            'sha': data_review['sha'],
            'meta_sha': data_meta['sha'],
            'review_status': review_status,
            'review_status_author': review_status_author,
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
    remember_review_preferences(response, reference_language, review_language, key)
    return response


@app.post('/save/{key}')
def save_question(
    request: Request,
    key: str,
    sha: str = Form(...),
    meta_sha: str = Form(...),
    comments_sha: str = Form(''),
    action: str = Form(...),
    question: Optional[str] = Form(None),
    answer_a: Optional[str] = Form(None),
    answer_b: Optional[str] = Form(None),
    answer_c: Optional[str] = Form(None),
    answer_d: Optional[str] = Form(None),
    comment: Optional[str] = Form(None),
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
        expected_head = ensure_campaign_snapshot(token)['head_sha']
        reviewer = request.session.get('username') or 'unknown'

        meta_path = f'pool/questions/{question_id}/question.meta.json'
        current_meta = fetch_path(CAMPAIGN_BRANCH, meta_path, token)
        if current_meta['sha'] != meta_sha:
            return HTMLResponse(
                '<h1>Concurrent change detected</h1><p>Reload the question before continuing.</p>',
                status_code=409,
            )

        if action == 'reopen':
            updated_meta = meta_with_status(current_meta['json'], question_id, review_language, 'to_be_reviewed')
            if updated_meta != current_meta['json']:
                commit_campaign_files(
                    {meta_path: updated_meta},
                    f'Reopen {key} {review_language} review',
                    expected_head,
                    token,
                )
                updated_meta_file = fetch_path(CAMPAIGN_BRANCH, meta_path, token)
                STATUS_AUTHOR_CACHE[(meta_path, review_language, updated_meta_file['sha'])] = reviewer
            return RedirectResponse(edit_url(key, reference_language, review_language), status_code=303)

        if action != 'commit':
            raise ValueError(f'Unsupported review action: {action}.')

        content_path = f'pool/questions/{question_id}/question.{review_language}.json'
        current_content = fetch_path(CAMPAIGN_BRANCH, content_path, token)
        if current_content['sha'] != sha:
            return HTMLResponse(
                '<h1>Concurrent change detected</h1><p>Reload the question before committing.</p>',
                status_code=409,
            )
        updated_content = content_with_edits(
            current_content['json'],
            question_id,
            review_language,
            {
                'question': question,
                'answer_a': answer_a,
                'answer_b': answer_b,
                'answer_c': answer_c,
                'answer_d': answer_d,
            },
        )

        comment_text = comment.strip() if comment else ''
        current_comments = None
        if comment_text:
            comments_path = f'reviews/{question_id}.json'
            current_comments = fetch_optional_path(CAMPAIGN_BRANCH, comments_path, token)
            current_comments_sha = current_comments['sha'] if current_comments is not None else ''
            if current_comments_sha != comments_sha:
                return HTMLResponse(
                    '<h1>Concurrent change detected</h1><p>Reload the question before committing.</p>',
                    status_code=409,
                )

        changes = {}
        if updated_content != current_content['json']:
            changes[content_path] = updated_content
        if comment_text:
            updated_comments = comment_with_append(current_comments, question_id, review_language, comment_text)
            changes[comments_path] = updated_comments

        updated_meta = meta_with_status(current_meta['json'], question_id, review_language, 'approved')
        if updated_meta != current_meta['json']:
            changes[meta_path] = updated_meta
        if changes:
            commit_campaign_files(
                changes,
                f'Commit {key} {review_language} review',
                expected_head,
                token,
            )
            if meta_path in changes:
                updated_meta_file = fetch_path(CAMPAIGN_BRANCH, meta_path, token)
                STATUS_AUTHOR_CACHE[(meta_path, review_language, updated_meta_file['sha'])] = reviewer
            if comment_text:
                updated_comments_file = fetch_path(CAMPAIGN_BRANCH, comments_path, token)
                old_comment_sha = current_comments['sha'] if current_comments is not None else ''
                previous_authors = COMMENT_AUTHOR_CACHE.get(
                    (comments_path, review_language, old_comment_sha),
                    ['unknown'] * (len(updated_comments['comments'][review_language]) - 1),
                )
                COMMENT_AUTHOR_CACHE[
                    (comments_path, review_language, updated_comments_file['sha'])
                ] = [*previous_authors, reviewer]
    except ValueError as exc:
        return HTMLResponse(f'<h1>Invalid campaign data</h1><pre>{exc}</pre>', status_code=400)
    except CampaignConflictError:
        return HTMLResponse(
            '<h1>Concurrent change detected</h1><p>The campaign was refreshed. Reload the question.</p>',
            status_code=409,
        )
    except CampaignWriteError as exc:
        return HTMLResponse(f'<h1>GitHub write failed</h1><pre>{exc}</pre>', status_code=502)
    except requests.exceptions.HTTPError as exc:
        status_code = 409 if exc.response is not None and exc.response.status_code in (409, 422) else 502
        return HTMLResponse(f'<h1>GitHub write failed</h1><pre>{exc}</pre>', status_code=status_code)
    return RedirectResponse(edit_url(key, reference_language, review_language), status_code=303)
