import os
import base64
from collections import defaultdict
from contextvars import ContextVar
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
import re
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
CAMPAIGNS_JSON = os.getenv('CAMPAIGNS_JSON')
CAMPAIGNS_FILE = os.getenv('CAMPAIGNS_FILE')
DEFAULT_CAMPAIGN = os.getenv('DEFAULT_CAMPAIGN', 'default')
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
EDITABLE_METADATA_FIELDS = (
    '/class_level',
    '/HB/rationale',
    '/HB/motivation',
)
PICTURE_FIELDS = (
    'picture_question_url',
    'picture_answer_a_url',
    'picture_answer_b_url',
    'picture_answer_c_url',
    'picture_answer_d_url',
)
PICTURE_FIELD_LABELS = {
    'picture_question_url': 'Question illustration',
    'picture_answer_a_url': 'Answer A illustration',
    'picture_answer_b_url': 'Answer B illustration',
    'picture_answer_c_url': 'Answer C illustration',
    'picture_answer_d_url': 'Answer D illustration',
}
VALID_CLASS_LEVELS = (0, 1, 9)
PREFERENCE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60
REFERENCE_LANGUAGE_COOKIE = '50ohm_reference_language'
REVIEW_LANGUAGE_COOKIE = '50ohm_review_language'
LAST_QUESTION_COOKIE = '50ohm_last_question'
PROFILE_REQUEST_ID = ContextVar('profile_request_id', default='-')
PROFILE_EVENTS = ContextVar('profile_events', default=None)
LOGGER = logging.getLogger('uvicorn.error')
CAMPAIGN_SNAPSHOTS = {}
CAMPAIGN_SNAPSHOT_LOCK = threading.Lock()
STATUS_AUTHOR_CACHE = {}
COMMENT_AUTHOR_CACHE = {}

required_config = {
    'GITHUB_CLIENT_ID': CLIENT_ID,
    'GITHUB_CLIENT_SECRET': CLIENT_SECRET,
    'GITHUB_OWNER': OWNER,
    'GITHUB_REPO': REPO,
    'GITHUB_CALLBACK_URL': CALLBACK_URL,
    'SESSION_SECRET': SESSION_SECRET,
}
missing_config = [key for key, value in required_config.items() if not value]
if missing_config:
    raise RuntimeError(f"Missing required configuration: {', '.join(missing_config)}")


def load_campaign_configs(raw_json, legacy_branch, default_campaign, config_file=None):
    source_name = 'CAMPAIGNS_JSON'
    if config_file:
        source_name = f'CAMPAIGNS_FILE ({config_file})'
        try:
            raw_json = Path(config_file).read_text(encoding='utf-8')
        except OSError as exc:
            raise RuntimeError(f'Unable to read {source_name}: {exc}') from exc

    if raw_json:
        try:
            raw_configs = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f'{source_name} must contain valid JSON.') from exc
        if not isinstance(raw_configs, dict) or not raw_configs:
            raise RuntimeError(f'{source_name} must contain a non-empty JSON object.')
    elif legacy_branch:
        raw_configs = {default_campaign: {'branch': legacy_branch, 'label': default_campaign}}
    else:
        raise RuntimeError('Set CAMPAIGNS_FILE, CAMPAIGNS_JSON, or CAMPAIGN_BRANCH.')

    configs = {}
    for campaign_id, raw_config in raw_configs.items():
        if not isinstance(campaign_id, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', campaign_id):
            raise RuntimeError(f'Invalid campaign id: {campaign_id!r}.')
        if isinstance(raw_config, str):
            raw_config = {'branch': raw_config}
        if not isinstance(raw_config, dict):
            raise RuntimeError(f'Campaign {campaign_id} configuration must be an object or branch string.')
        branch = raw_config.get('branch')
        if not isinstance(branch, str) or not branch.strip():
            raise RuntimeError(f'Campaign {campaign_id} has no valid branch.')
        label = raw_config.get('label', campaign_id)
        if not isinstance(label, str) or not label.strip():
            raise RuntimeError(f'Campaign {campaign_id} has no valid label.')
        configs[campaign_id] = {'branch': branch, 'label': label}
    if default_campaign not in configs:
        raise RuntimeError(f'DEFAULT_CAMPAIGN {default_campaign!r} is not configured.')
    return configs


CAMPAIGNS = load_campaign_configs(
    CAMPAIGNS_JSON,
    CAMPAIGN_BRANCH,
    DEFAULT_CAMPAIGN,
    CAMPAIGNS_FILE,
)


def campaign_config(campaign_id):
    try:
        return CAMPAIGNS[campaign_id]
    except KeyError as exc:
        raise ValueError(f'Unknown campaign: {campaign_id}.') from exc


def campaign_branch(campaign_id):
    return campaign_config(campaign_id)['branch']

app = FastAPI()
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=os.getenv('SESSION_HTTPS_ONLY', 'true').lower() == 'true',
    same_site='lax',
)
app.mount('/static', StaticFiles(directory='static'), name='static')
templates = Jinja2Templates(directory='templates')
STATIC_VERSION = hashlib.sha256(Path('static/style.css').read_bytes()).hexdigest()[:12]
templates.env.globals['static_version'] = STATIC_VERSION


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


def oldest_campaign_commit_for_path(campaign_id, path, token):
    branch = campaign_branch(campaign_id)
    response = github_request(
        'GET',
        f'https://api.github.com/repos/{OWNER}/{REPO}/commits',
        operation='commits.oldest',
        resource=path,
        params={'sha': branch, 'path': path, 'per_page': 1},
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


def campaign_branch_head(campaign_id, token):
    branch = campaign_branch(campaign_id)
    ref = quote(f'heads/{branch}', safe='/')
    response = github_request(
        'GET',
        f'https://api.github.com/repos/{OWNER}/{REPO}/git/ref/{ref}',
        operation='branch.read',
        resource=branch,
        headers=github_headers(token),
        timeout=15,
    )
    response.raise_for_status()
    sha = response.json().get('object', {}).get('sha')
    if not sha:
        raise ValueError(f'Cannot resolve campaign branch head: {branch}.')
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


def invalidate_campaign_snapshot(campaign_id):
    with CAMPAIGN_SNAPSHOT_LOCK:
        CAMPAIGN_SNAPSHOTS.pop(campaign_id, None)


def ensure_campaign_snapshot(campaign_id, token):
    now = time.monotonic()
    snapshot = CAMPAIGN_SNAPSHOTS.get(campaign_id)
    if (
        snapshot is not None
        and now - snapshot['checked_at'] < CAMPAIGN_REFRESH_SECONDS
    ):
        return snapshot
    with CAMPAIGN_SNAPSHOT_LOCK:
        now = time.monotonic()
        snapshot = CAMPAIGN_SNAPSHOTS.get(campaign_id)
        if (
            snapshot is not None
            and now - snapshot['checked_at'] < CAMPAIGN_REFRESH_SECONDS
        ):
            return snapshot
        head_sha = campaign_branch_head(campaign_id, token)
        if snapshot is not None and snapshot['head_sha'] == head_sha:
            snapshot['checked_at'] = now
            return snapshot
        if snapshot is not None:
            snapshot = {
                **snapshot,
                'head_sha': head_sha,
                'current_files': download_campaign_snapshot(head_sha, token),
                'checked_at': now,
            }
            CAMPAIGN_SNAPSHOTS[campaign_id] = snapshot
            return snapshot
        export_sha = oldest_campaign_commit_for_path(campaign_id, 'campaign.meta.json', token)
        current_files = download_campaign_snapshot(head_sha, token)
        original_files = download_campaign_snapshot(export_sha, token)
        snapshot = {
            'head_sha': head_sha,
            'export_sha': export_sha,
            'current_files': current_files,
            'original_files': original_files,
            'checked_at': now,
        }
        CAMPAIGN_SNAPSHOTS[campaign_id] = snapshot
        return snapshot


def fetch_path(campaign_id, ref, path, token):
    if ref == campaign_branch(campaign_id):
        snapshot = ensure_campaign_snapshot(campaign_id, token)
        try:
            return snapshot['current_files'][path]
        except KeyError as exc:
            raise ValueError(f'Campaign path does not exist: {path}.') from exc
    return fetch_repository_path(f'{OWNER}/{REPO}', ref, path, token)


def fetch_original_question(campaign_id, manifest, question_id, language, token):
    if question_id not in manifest.get('question_ids', []):
        raise ValueError(f'Question {question_id} is outside the campaign scope.')
    path = f'pool/questions/{question_id}/question.{language}.json'
    snapshot = ensure_campaign_snapshot(campaign_id, token)
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


def commit_campaign_files(campaign_id, changes, message, expected_head, token):
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
                        'branchName': campaign_branch(campaign_id),
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
            invalidate_campaign_snapshot(campaign_id)
            raise CampaignConflictError(error_message)
        raise CampaignWriteError(error_message)
    commit_sha = payload.get('data', {}).get('createCommitOnBranch', {}).get('commit', {}).get('oid')
    if not commit_sha:
        raise CampaignWriteError('GitHub did not return the created commit oid.')

    with CAMPAIGN_SNAPSHOT_LOCK:
        snapshot = CAMPAIGN_SNAPSHOTS.get(campaign_id)
        if snapshot is None or snapshot['head_sha'] != expected_head:
            invalidate_after_lock = True
        else:
            invalidate_after_lock = False
            for path, content in changes.items():
                raw = serialized_json(content)
                snapshot['current_files'][path] = {
                    'sha': git_blob_sha(raw),
                    'json': content,
                }
            snapshot['head_sha'] = commit_sha
            snapshot['checked_at'] = time.monotonic()
    if invalidate_after_lock:
        invalidate_campaign_snapshot(campaign_id)
    return commit_sha


def fetch_optional_path(campaign_id, ref, path, token):
    if ref == campaign_branch(campaign_id):
        return ensure_campaign_snapshot(campaign_id, token)['current_files'].get(path)
    try:
        return fetch_path(campaign_id, ref, path, token)
    except requests.exceptions.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise


def github_commits_for_path(campaign_id, path, token):
    response = github_request(
        'GET',
        f'https://api.github.com/repos/{OWNER}/{REPO}/commits',
        operation='commits.list',
        resource=path,
        params={'sha': campaign_branch(campaign_id), 'path': path, 'per_page': 100},
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


def status_author(campaign_id, path, language, token):
    branch = campaign_branch(campaign_id)
    current_file = fetch_path(campaign_id, branch, path, token)
    cache_key = (campaign_id, path, language, current_file['sha'])
    if cache_key in STATUS_AUTHOR_CACHE:
        return STATUS_AUTHOR_CACHE[cache_key]
    for commit in github_commits_for_path(campaign_id, path, token):
        current = fetch_optional_path(campaign_id, commit['sha'], path, token)
        if current is None:
            continue
        current_status = current['json'].get('review', {}).get(language)
        parents = commit.get('parents', [])
        previous_status = None
        if parents:
            previous = fetch_optional_path(campaign_id, parents[0]['sha'], path, token)
            if previous is not None:
                previous_status = previous['json'].get('review', {}).get(language)
        if current_status != previous_status:
            author = commit_author(commit)
            STATUS_AUTHOR_CACHE[cache_key] = author
            return author
    STATUS_AUTHOR_CACHE[cache_key] = 'unknown'
    return 'unknown'


def load_comments(campaign_id, question_id, language, token):
    path = f'reviews/{question_id}.json'
    current = fetch_optional_path(campaign_id, campaign_branch(campaign_id), path, token)
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

    cache_key = (campaign_id, path, language, current['sha'])
    if cache_key in COMMENT_AUTHOR_CACHE:
        authors = COMMENT_AUTHOR_CACHE[cache_key]
        return current['sha'], [
            {'text': text, 'author': authors[index]}
            for index, text in enumerate(comments)
        ]

    authors = ['unknown'] * len(comments)
    previous_count = 0
    for commit in reversed(github_commits_for_path(campaign_id, path, token)):
        version = fetch_optional_path(campaign_id, commit['sha'], path, token)
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


def media_url(media_manifest, media_id, language):
    if media_id is None:
        return None
    if type(media_id) is not int or media_id <= 0:
        raise ValueError(f'Invalid question media id: {media_id!r}.')
    if media_manifest.get('schema_version') != 1:
        raise ValueError('Unsupported media manifest schema_version.')
    repository = media_manifest.get('repository')
    revision = media_manifest.get('revision')
    if (
        not isinstance(repository, str)
        or len(repository.split('/')) != 2
        or not all(repository.split('/'))
        or not isinstance(revision, str)
        or re.fullmatch(r'[0-9a-f]{40}', revision) is None
    ):
        raise ValueError('Campaign media repository or revision is invalid.')
    item = media_manifest.get('items', {}).get(str(media_id))
    if not isinstance(item, dict):
        raise ValueError(f'Campaign media manifest has no item {media_id}.')
    variant = item.get('variants', {}).get(language)
    if not isinstance(variant, dict):
        raise ValueError(f'Campaign media item {media_id} has no {language} variant.')
    path = variant.get('path')
    if (
        not isinstance(path, str)
        or not path
        or path.startswith('/')
        or '..' in Path(path).parts
        or variant.get('media_type') != 'image/svg+xml'
    ):
        raise ValueError(f'Campaign media item {media_id}/{language} has an invalid path or type.')
    owner, repo = repository.split('/')
    return (
        'https://raw.githubusercontent.com/'
        f'{quote(owner, safe="")}/{quote(repo, safe="")}/'
        f'{quote(revision, safe="")}/{quote(path, safe="/")}'
    )


def question_media_urls(question, language, media_manifest):
    return {
        field: media_url(media_manifest, question[field], language)
        for field in ('picture_question', 'picture_a', 'picture_b', 'picture_c', 'picture_d')
    }


def editable_field_list(manifest, name, supported):
    values = manifest.get(name, [])
    if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
        raise ValueError(f'Campaign {name} must be an array of strings.')
    if len(set(values)) != len(values):
        raise ValueError(f'Campaign {name} contains duplicates.')
    unknown = [value for value in values if value not in supported]
    if unknown:
        raise ValueError(f'Campaign {name} contains unsupported fields: {", ".join(unknown)}')
    return list(values)


def media_options(media_manifest, language):
    items = media_manifest.get('items', {})
    if not isinstance(items, dict):
        raise ValueError('Campaign media manifest has an invalid items object.')
    options = []
    for raw_id in items:
        if not str(raw_id).isdigit() or int(raw_id) <= 0:
            raise ValueError(f'Campaign media manifest has an invalid media id: {raw_id!r}.')
        media_id = int(raw_id)
        options.append({'id': media_id, 'url': media_url(media_manifest, media_id, language)})
    return sorted(options, key=lambda item: item['id'])


def metadata_with_edits(meta, question_id, editable_fields, values):
    if meta.get('id') != question_id:
        raise ValueError('Question metadata id does not match its directory.')
    result = dict(meta)
    if '/class_level' in editable_fields:
        raw_class_level = values.get('/class_level')
        try:
            class_level = int(raw_class_level)
        except (TypeError, ValueError) as exc:
            raise ValueError('class_level must be 0, 1, or 9.') from exc
        if class_level not in VALID_CLASS_LEVELS:
            raise ValueError('class_level must be 0, 1, or 9.')
        result['class_level'] = class_level

    hb = dict(result.get('HB', {}))
    if '/HB/rationale' in editable_fields:
        rationale = [item.strip() for item in (values.get('/HB/rationale') or []) if item.strip()]
        if rationale:
            hb['rationale'] = rationale
        else:
            hb.pop('rationale', None)
    if '/HB/motivation' in editable_fields:
        motivation = (values.get('/HB/motivation') or '').strip()
        if motivation:
            hb['motivation'] = motivation
        else:
            hb.pop('motivation', None)
    if hb:
        result['HB'] = hb
    else:
        result.pop('HB', None)
    return result


def content_with_edits(
    content,
    question_id,
    language,
    values,
    editable_picture_fields=None,
    picture_values=None,
    media_manifest=None,
):
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
        elif submitted_value is None and current_value == '':
            result[field] = current_value
        elif submitted_value is None:
            raise ValueError(f'Missing editable field: {field}.')
        else:
            result[field] = submitted_value

    if not result['question'].strip():
        raise ValueError('Question text cannot be empty.')

    editable_picture_fields = editable_picture_fields or []
    picture_values = picture_values or {}
    available_media = media_manifest.get('items', {}) if isinstance(media_manifest, dict) else {}
    for field in editable_picture_fields:
        raw_value = picture_values.get(field)
        if raw_value in (None, ''):
            result[field] = None
            continue
        try:
            media_id = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{field} must contain a valid media id or be empty.') from exc
        if media_id <= 0 or str(media_id) not in available_media:
            raise ValueError(f'{field} references media outside media.refs.json: {media_id}.')
        media_url(media_manifest, media_id, language)
        result[field] = media_id

    if editable_picture_fields:
        for text_field, picture_field in zip(
            ('question', 'answer_a', 'answer_b', 'answer_c', 'answer_d'),
            PICTURE_FIELDS,
            strict=True,
        ):
            if result.get(text_field) is None and result.get(picture_field) is None:
                raise ValueError(f'{text_field} cannot be null without {picture_field}.')
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


def campaign_url(campaign_id):
    return f'/campaign/{quote(campaign_id, safe="")}/'


def edit_url(campaign_id, key, reference_language, review_language):
    query = urlencode({
        'reference_language': reference_language,
        'review_language': review_language,
    })
    return f'{campaign_url(campaign_id)}edit/{quote(key, safe="")}?{query}'


def select_languages(manifest, requested_reference=None, requested_review=None):
    languages = manifest.get('languages', [])
    editable_languages = manifest.get('editable_languages', [])
    if not languages:
        raise ValueError('A review campaign requires at least one language.')
    if not editable_languages or any(language not in languages for language in editable_languages):
        raise ValueError('Campaign editable_languages must be a non-empty subset of languages.')

    review_language = requested_review or ('fr' if 'fr' in editable_languages else editable_languages[0])
    if review_language not in editable_languages:
        raise ValueError(f'Language {review_language} is not editable in this campaign.')

    reference_language = requested_reference or ('de' if 'de' in languages else languages[0])
    if reference_language not in languages:
        raise ValueError(f'Language {reference_language} is not available in this campaign.')
    return reference_language, review_language


def validate_campaign_navigation(navigation, navigation_index, manifest):
    error = 'Campaign navigation must contain a non-empty chapter hierarchy ending in questions.'
    if not isinstance(navigation, dict) or not isinstance(navigation.get('sections'), list):
        raise ValueError(error)

    navigation_numbers = []
    chapters = navigation['sections']
    if not chapters:
        raise ValueError(error)

    def collect(node):
        if not isinstance(node, dict) or not isinstance(node.get('title'), str) or not node['title']:
            raise ValueError(error)
        sections = node.get('sections')
        questions = node.get('questions')
        has_sections = isinstance(sections, list) and bool(sections)
        has_questions = isinstance(questions, list) and bool(questions)
        if has_sections == has_questions:
            raise ValueError(error)
        if has_sections:
            for child in sections:
                collect(child)
            return
        for question in questions:
            number = question.get('number') if isinstance(question, dict) else None
            if not isinstance(number, str) or not number:
                raise ValueError(error)
            navigation_numbers.append(number)

    for chapter in chapters:
        collect(chapter)

    if len(set(navigation_numbers)) != len(navigation_numbers):
        raise ValueError('Campaign navigation contains duplicate question numbers.')
    items = navigation_index.get('items') if isinstance(navigation_index, dict) else None
    if not isinstance(items, list):
        raise ValueError('Campaign navigation index must contain an items array.')
    index_numbers = [item.get('internal_code') for item in items if isinstance(item, dict)]
    index_question_ids = [item.get('question_id') for item in items if isinstance(item, dict)]
    if (
        len(index_numbers) != len(items)
        or any(not isinstance(number, str) or not number for number in index_numbers)
        or len(set(index_numbers)) != len(index_numbers)
        or set(index_numbers) != set(navigation_numbers)
    ):
        raise ValueError('Campaign navigation index does not match the localized navigation catalog.')
    manifest_question_ids = manifest.get('question_ids')
    if (
        not isinstance(manifest_question_ids, list)
        or len(index_question_ids) != len(items)
        or any(not isinstance(question_id, str) or not question_id for question_id in index_question_ids)
        or len(set(index_question_ids)) != len(index_question_ids)
        or set(index_question_ids) != set(manifest_question_ids)
    ):
        raise ValueError('Campaign navigation index does not match campaign question_ids.')


def load_campaign(campaign_id, token, requested_reference=None, requested_review=None, manifest=None):
    branch = campaign_branch(campaign_id)
    if manifest is None:
        manifest = fetch_path(campaign_id, branch, 'campaign.meta.json', token)['json']
    if manifest.get('campaign_branch') != branch:
        raise ValueError('Configured branch does not match campaign.meta.json.')
    editable_field_list(manifest, 'editable_metadata_fields', EDITABLE_METADATA_FIELDS)
    editable_field_list(manifest, 'editable_picture_fields', PICTURE_FIELDS)
    reference_language, review_language = select_languages(
        manifest,
        requested_reference,
        requested_review,
    )
    navigation = fetch_path(
        campaign_id,
        branch,
        f'derived/question_pool_ch-{reference_language}.json',
        token,
    )['json']
    navigation_index = fetch_path(
        campaign_id,
        branch,
        'derived/navigation.index.json',
        token,
    )['json']
    validate_campaign_navigation(navigation, navigation_index, manifest)
    campaign_toc = toc(navigation)
    questions_by_number = {}
    for item in navigation_index['items']:
        question_id = item['question_id']
        number = item['internal_code']
        meta_path = f'pool/questions/{question_id}/question.meta.json'
        current_meta = fetch_path(campaign_id, branch, meta_path, token)['json']
        if current_meta.get('id') != question_id:
            raise ValueError(f'Question metadata id does not match {question_id}.')
        current_review = current_meta.get('review', {})
        questions_by_number[number] = {
            'question_id': question_id,
            'review': current_review,
        }
        if current_review.get(review_language) == 'approved':
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


@app.get('/')
def root():
    return RedirectResponse(campaign_url(DEFAULT_CAMPAIGN))


@app.get('/campaign/{campaign_id}/', response_class=HTMLResponse)
def index(request: Request, campaign_id: str):
    try:
        config = campaign_config(campaign_id)
    except ValueError as exc:
        return HTMLResponse(f'<h1>Campaign not found</h1><pre>{exc}</pre>', status_code=404)
    logged_in = bool(get_token(request))
    if logged_in:
        try:
            manifest = fetch_path(
                campaign_id,
                config['branch'],
                'campaign.meta.json',
                get_token(request),
            )['json']
            requested_reference, requested_review = requested_languages(request, manifest)
            manifest, campaign_toc, questions_by_number, reference_language, review_language = load_campaign(
                campaign_id,
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
            'campaign_id': campaign_id,
            'campaign_label': config['label'],
        },
    )
    if logged_in:
        remember_review_preferences(response, reference_language, review_language)
    return response


@app.get('/healthz')
def healthz():
    return {'status': 'ok'}


@app.get('/login')
def login(request: Request, campaign_id: str = DEFAULT_CAMPAIGN):
    try:
        campaign_config(campaign_id)
    except ValueError as exc:
        return HTMLResponse(f'<h1>Campaign not found</h1><pre>{exc}</pre>', status_code=404)
    state = secrets.token_urlsafe(32)
    request.session['oauth_state'] = state
    request.session['oauth_campaign_id'] = campaign_id
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
    campaign_id = request.session.pop('oauth_campaign_id', DEFAULT_CAMPAIGN)
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
    return RedirectResponse(campaign_url(campaign_id))


@app.get('/logout')
def logout(request: Request, campaign_id: str = DEFAULT_CAMPAIGN):
    request.session.clear()
    return RedirectResponse(campaign_url(campaign_id))

# Extract GET parameter (used in forms) and redirect
@app.get('/campaign/{campaign_id}/edit', response_class=HTMLResponse)
def edit_question_redirect(request: Request, campaign_id: str):
    return edit_question(request, campaign_id, request.query_params['key'])

@app.get('/campaign/{campaign_id}/edit/{key}', response_class=HTMLResponse)
def edit_question(request: Request, campaign_id: str, key: str):
    token = get_token(request)
    if not token:
        return RedirectResponse(f'/login?{urlencode({"campaign_id": campaign_id})}')

    try:
        branch = campaign_branch(campaign_id)
        manifest = fetch_path(campaign_id, branch, 'campaign.meta.json', token)['json']
        requested_reference, requested_review = requested_languages(request, manifest)
        manifest, campaign_toc, questions_by_number, reference_language, review_language = load_campaign(
            campaign_id,
            token,
            requested_reference,
            requested_review,
            manifest,
        )
        if key not in questions_by_number:
            return HTMLResponse('<h1>Question not found in campaign</h1>', status_code=404)
        question_id = questions_by_number[key]['question_id']
        data_reference = fetch_path(
            campaign_id,
            branch,
            f'pool/questions/{question_id}/question.{reference_language}.json',
            token,
        )
        data_review = fetch_path(
            campaign_id,
            branch,
            f'pool/questions/{question_id}/question.{review_language}.json',
            token,
        )
        data_original = fetch_original_question(campaign_id, manifest, question_id, review_language, token)
        media_manifest = fetch_path(campaign_id, branch, 'media.refs.json', token)['json']
        editable_metadata_fields = editable_field_list(
            manifest,
            'editable_metadata_fields',
            EDITABLE_METADATA_FIELDS,
        )
        editable_picture_fields = editable_field_list(
            manifest,
            'editable_picture_fields',
            PICTURE_FIELDS,
        )
        data_meta = fetch_path(
            campaign_id,
            branch,
            f'pool/questions/{question_id}/question.meta.json',
            token,
        )
        reference = canonical_to_legacy_question(data_reference['json'])
        review = canonical_to_legacy_question(data_review['json'])
        original = canonical_to_legacy_question(data_original['json'])
        reference_media = question_media_urls(reference, reference_language, media_manifest)
        review_media = question_media_urls(review, review_language, media_manifest)
        review_status = data_meta['json'].get('review', {}).get(review_language)
        meta_path = f'pool/questions/{question_id}/question.meta.json'
        review_status_author = status_author(campaign_id, meta_path, review_language, token)
        comments_sha, comments = load_comments(campaign_id, question_id, review_language, token)
    except (requests.exceptions.HTTPError, ValueError) as e:
        return HTMLResponse(f'<h1>Error</h1><pre>{e.args[0]}</pre>')

    response = templates.TemplateResponse(
        request=request,
        name='editor.html',
        context={
            'key': key,
            'question_id': question_id,
            'reference': reference,
            'review': review,
            'review_content': data_review['json'],
            'reference_media': reference_media,
            'review_media': review_media,
            'diff': word_diff(original, review),
            'sha': data_review['sha'],
            'meta_sha': data_meta['sha'],
            'review_status': review_status,
            'review_status_author': review_status_author,
            'comments_sha': comments_sha or '',
            'comments': comments,
            'question_meta': data_meta['json'],
            'rationales': data_meta['json'].get('HB', {}).get('rationale') or [],
            'editable_metadata_fields': editable_metadata_fields,
            'editable_picture_fields': editable_picture_fields,
            'details_enabled': bool(editable_metadata_fields or editable_picture_fields),
            'picture_field_labels': PICTURE_FIELD_LABELS,
            'picture_options': media_options(media_manifest, review_language),
            'review_picture_urls': {
                'picture_question_url': review_media['picture_question'],
                'picture_answer_a_url': review_media['picture_a'],
                'picture_answer_b_url': review_media['picture_b'],
                'picture_answer_c_url': review_media['picture_c'],
                'picture_answer_d_url': review_media['picture_d'],
            },
            'reference_language': reference_language,
            'review_language': review_language,
            'reference_language_label': LANGUAGE_LABELS.get(reference_language, reference_language.upper()),
            'review_language_label': LANGUAGE_LABELS.get(review_language, review_language.upper()),
            'campaign_id': campaign_id,
            'campaign_label': campaign_config(campaign_id)['label'],
            'next_question': campaign_toc.next_q_in_subsection(key),
            'prev_question': campaign_toc.prev_q_in_subsection(key),
            'next_section': campaign_toc.next_q_in_section(key),
            'prev_section': campaign_toc.prev_q_in_section(key)
        },
    )
    remember_review_preferences(response, reference_language, review_language, key)
    return response


@app.post('/campaign/{campaign_id}/save/{key}')
def save_question(
    request: Request,
    campaign_id: str,
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
    metadata_class_level: Optional[str] = Form(None),
    metadata_rationale: list[str] = Form([]),
    metadata_motivation: Optional[str] = Form(None),
    picture_question_url: Optional[str] = Form(None),
    picture_answer_a_url: Optional[str] = Form(None),
    picture_answer_b_url: Optional[str] = Form(None),
    picture_answer_c_url: Optional[str] = Form(None),
    picture_answer_d_url: Optional[str] = Form(None),
    comment: Optional[str] = Form(None),
):
    token = get_token(request)
    if not token:
        return RedirectResponse(f'/login?{urlencode({"campaign_id": campaign_id})}')
    reference_language = request.query_params.get('reference_language')
    review_language = request.query_params.get('review_language')
    try:
        manifest, _, questions_by_number, reference_language, review_language = load_campaign(
            campaign_id,
            token,
            reference_language,
            review_language,
        )
        if key not in questions_by_number:
            return HTMLResponse('<h1>Question not found in campaign</h1>', status_code=404)
        question_id = questions_by_number[key]['question_id']
        branch = campaign_branch(campaign_id)
        expected_head = ensure_campaign_snapshot(campaign_id, token)['head_sha']
        reviewer = request.session.get('username') or 'unknown'

        meta_path = f'pool/questions/{question_id}/question.meta.json'
        current_meta = fetch_path(campaign_id, branch, meta_path, token)
        if current_meta['sha'] != meta_sha:
            return HTMLResponse(
                '<h1>Concurrent change detected</h1><p>Reload the question before continuing.</p>',
                status_code=409,
            )

        if action == 'reopen':
            updated_meta = meta_with_status(current_meta['json'], question_id, review_language, 'to_be_reviewed')
            if updated_meta != current_meta['json']:
                commit_campaign_files(
                    campaign_id,
                    {meta_path: updated_meta},
                    f'Reopen {key} {review_language} review',
                    expected_head,
                    token,
                )
                updated_meta_file = fetch_path(campaign_id, branch, meta_path, token)
                STATUS_AUTHOR_CACHE[(campaign_id, meta_path, review_language, updated_meta_file['sha'])] = reviewer
            return RedirectResponse(edit_url(campaign_id, key, reference_language, review_language), status_code=303)

        if action != 'commit':
            raise ValueError(f'Unsupported review action: {action}.')

        editable_metadata_fields = editable_field_list(
            manifest,
            'editable_metadata_fields',
            EDITABLE_METADATA_FIELDS,
        )
        editable_picture_fields = editable_field_list(
            manifest,
            'editable_picture_fields',
            PICTURE_FIELDS,
        )
        media_manifest = (
            fetch_path(campaign_id, branch, 'media.refs.json', token)['json']
            if editable_picture_fields
            else {}
        )

        content_path = f'pool/questions/{question_id}/question.{review_language}.json'
        current_content = fetch_path(campaign_id, branch, content_path, token)
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
            editable_picture_fields=editable_picture_fields,
            picture_values={
                'picture_question_url': picture_question_url,
                'picture_answer_a_url': picture_answer_a_url,
                'picture_answer_b_url': picture_answer_b_url,
                'picture_answer_c_url': picture_answer_c_url,
                'picture_answer_d_url': picture_answer_d_url,
            },
            media_manifest=media_manifest,
        )

        comment_text = comment.strip() if comment else ''
        current_comments = None
        if comment_text:
            comments_path = f'reviews/{question_id}.json'
            current_comments = fetch_optional_path(campaign_id, branch, comments_path, token)
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

        updated_meta = metadata_with_edits(
            current_meta['json'],
            question_id,
            editable_metadata_fields,
            {
                '/class_level': metadata_class_level,
                '/HB/rationale': metadata_rationale,
                '/HB/motivation': metadata_motivation,
            },
        )
        updated_meta = meta_with_status(updated_meta, question_id, review_language, 'approved')
        if updated_meta != current_meta['json']:
            changes[meta_path] = updated_meta
        if changes:
            commit_campaign_files(
                campaign_id,
                changes,
                f'Commit {key} {review_language} review',
                expected_head,
                token,
            )
            if meta_path in changes:
                updated_meta_file = fetch_path(campaign_id, branch, meta_path, token)
                STATUS_AUTHOR_CACHE[(campaign_id, meta_path, review_language, updated_meta_file['sha'])] = reviewer
            if comment_text:
                updated_comments_file = fetch_path(campaign_id, branch, comments_path, token)
                old_comment_sha = current_comments['sha'] if current_comments is not None else ''
                previous_authors = COMMENT_AUTHOR_CACHE.get(
                    (campaign_id, comments_path, review_language, old_comment_sha),
                    ['unknown'] * (len(updated_comments['comments'][review_language]) - 1),
                )
                COMMENT_AUTHOR_CACHE[
                    (campaign_id, comments_path, review_language, updated_comments_file['sha'])
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
    return RedirectResponse(edit_url(campaign_id, key, reference_language, review_language), status_code=303)
