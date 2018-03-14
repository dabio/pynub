import bcrypt
import functools
import os
import psycopg2
import psycopg2.extras
import re
import urllib.parse

from datetime import datetime, timedelta
from flask import Flask, request, render_template, g, session, \
    redirect, url_for
from raven.contrib.flask import Sentry

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'super-secret-key')


SESSION_TOKEN = 'token'
EMAIL_RE = '.+@.+\..+'
MIN_PWD_LEN = 4
DELETE_ME_COOKIE = 'deleteMe'

# User Feeback
SIGNIN_NO_ACCOUNT = 'Invalid Email or Password.'
SIGNIN_WRONG_PASS = 'Invalid Email or Password.'

REGISTER_INVALID_EMAIL = 'Invalid Email.'
REGISTER_PWD_TOO_SHORT = 'Password is too short.'
REGISTER_PWD_DONT_MATCH = 'Passwords do not match.'
REGISTER_ACCOUNT_EXISTS = (
    'Account already exists. Would you like to sign in instead?'
)

PROFILE_INVALID_EMAIL = 'Passwords do not match.'
PROFILE_WRONG_PASSWORD = 'Invalid Password.'
PROFILE_PWD_DONT_MATCH = 'Passwords do not match.'


# Send app errors to Sentry
sentry_dsn = os.getenv('SENTRY_DSN')
if sentry_dsn is not None:
    Sentry(app, dsn=sentry_dsn)


# -------
# Helpers
# -------

def get_db():
    return g.get('_db', psycopg2.connect(
        dsn=os.getenv('DATABASE_URL'),
        cursor_factory=psycopg2.extras.DictCursor
    ))


def init_db():
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().execute(f.read())
    db.commit()


def query_db(query, args=(), one=False):
    db = get_db()
    cur = db.cursor()
    cur.execute(query, args)
    if query.lower().startswith(('insert ', 'update ', 'delete ')):
        db.commit()
    if query.lower().startswith('delete '):
        return None
    return cur.fetchone() if one else cur.fetchall()


def get_user_by_email(email):
    return query_db(
        'SELECT id, email, password, created_at FROM users WHERE email = %s',
        (email, ), one=True)


def get_user_by_token(token):
    return query_db((
        'SELECT id, email, password, u.created_at, active_at, token'
        ' FROM users u JOIN logins l ON u.id = l.user_id AND l.token = %s'
        ' LIMIT 1'), (token, ), one=True)


def create_user(email, password_hash):
    res = query_db(
        'INSERT INTO users (email, password) VALUES (%s, %s) RETURNING id',
        (email, password_hash), one=True)
    return res['id']


def update_user_password(user_id, password_hash):
    res = query_db(
        'UPDATE users SET password = %s WHERE id = %s RETURNING id',
        (password_hash, user_id), one=True)
    return res['id']


def refresh_token(token):
    query_db((
        'UPDATE logins SET active_at = now() WHERE token = %s'
        ' RETURNING active_at'), (token, ))


def add_token(user_id):
    res = query_db(
        'INSERT INTO logins (user_id) VALUES (%s) RETURNING token',
        (user_id, ), one=True)
    return res['token']


def get_link(url):
    return query_db(
        'SELECT id FROM links WHERE url = %s LIMIT 1', (url, ), one=True)


def create_link(url):
    res = query_db(
        'INSERT INTO links (url) VALUES (%s) RETURNING id', (url, ), one=True)
    return res['id']


def get_link_for_user(link_id, user_id):
    return query_db((
        'SELECT created_at FROM user_links WHERE link_id = %s AND user_id = %s'
        ' LIMIT 1'), (link_id, user_id), one=True)


def create_link_for_user(url, user_id):
    link = get_link(url)
    if link is None:
        link_id = create_link(url)
    else:
        link_id = link['id']

    res = get_link_for_user(link_id, user_id)
    if res is None:
        res = query_db((
            'INSERT INTO user_links (link_id, user_id) VALUES (%s, %s)'
            ' RETURNING created_at'), (link_id, user_id), one=True)

    return res


def delete_link_for_user(link_id, user_id):
    query_db(
        'DELETE FROM user_links WHERE user_id = %s AND link_id = %s',
        (user_id, link_id))
    query_db((
        'DELETE FROM links WHERE id = %s AND'
        ' (SELECT count(link_id) FROM user_links WHERE link_id = %s) = 0'),
        (link_id, link_id))


def hash(password):
    return bcrypt.hashpw(
        password.encode('utf-8'), bcrypt.gensalt(10, b"2a")).decode('utf-8')


def verify(password, hash):
    return bcrypt.checkpw(
        password.encode('utf-8'), hash.encode('utf-8'))


# ----------
# Decorators
# ----------

def private(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            return redirect(url_for('signin'))
        return f(*args, **kwargs)
    return decorated_function


def public(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is not None:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# -------
# Signals
# -------

@app.before_request
def track_start_time():
    request.start_time = datetime.utcnow()


@app.before_request
def preload_user():
    g.user = None
    if SESSION_TOKEN in session:
        g.user = get_user_by_token(session[SESSION_TOKEN])


@app.before_request
def prolong_session():
    session.permanent = True


@app.before_request
def delete_links():
    if g.user is None:
        return

    cookie = request.cookies.get(DELETE_ME_COOKIE)
    if cookie is None:
        return

    links = cookie.split(',')
    for link_id in links:
        delete_link_for_user(link_id, g.user['id'])


@app.after_request
def show_processed_time(response):
    diff = (datetime.utcnow() - request.start_time).total_seconds()
    response.headers['X-Processed-Time'] = f"{diff * 1000:.2f}ms"
    return response


@app.teardown_request
def refresh_user_token(exception):
    if g.user is not None:
        refresh_token(g.user['token'])


@app.teardown_appcontext
def close_database(exception):
    if hasattr(g, '_db'):
        get_db().close()


# ------
# Routes
# ------

@app.route('/')
def index():
    if g.user is None:
        return render_template('home.html')
    return render_template('links.html', links=query_db((
        'SELECT id, url, ul.created_at FROM links l'
        ' JOIN user_links ul ON l.id = ul.link_id AND ul.user_id = %s'
        ' ORDER BY ul.created_at DESC'),
        (g.user['id'], )))


@app.route('/signin')
@public
@functools.lru_cache(512)
def signin():
    return render_template('signin.html')


@app.route('/signin', methods=['POST'])
@public
def post_signin():
    user = get_user_by_email(request.form.get('email'))
    if user is None:
        return render_template('signin.html', error=SIGNIN_NO_ACCOUNT)

    if not verify(request.form.get('password'), user['password']):
        return render_template('signin.html', error=SIGNIN_WRONG_PASS)

    session[SESSION_TOKEN] = add_token(user['id'])
    return redirect(url_for('index'))


@app.route('/register')
@functools.lru_cache(512)
@public
def register():
    return render_template('register.html')


@app.route('/register', methods=['POST'])
@public
def post_register():
    email = request.form.get('email')
    passw = request.form.get('password')

    user = get_user_by_email(email)
    if user is not None:
        return render_template('register.html', error=REGISTER_ACCOUNT_EXISTS)

    if re.search(EMAIL_RE, email) is None:
        return render_template('register.html', error=REGISTER_INVALID_EMAIL)

    if len(passw) < MIN_PWD_LEN:
        return render_template('register.html', error=REGISTER_PWD_TOO_SHORT)

    if passw != request.form.get('password_confirm'):
        return render_template('register.html', error=REGISTER_PWD_DONT_MATCH)

    session[SESSION_TOKEN] = add_token(create_user(email, hash(passw)))
    return redirect(url_for('index'))


@app.route('/signout')
@private
def signout():
    session.pop(SESSION_TOKEN, None)
    return redirect(url_for('index'))


@app.route('/profile')
@private
def profile():
    return render_template('profile.html')


@app.route('/profile', methods=['POST'])
@private
def post_profile():
    if not verify(request.form.get('password'), g.user['password']):
        render_template('profile.html', error=PROFILE_WRONG_PASSWORD)

    passw = request.form.get('password')

    # curr = request.form.get('current_password')

    if request.form.get('current_password') == g.user['password']:
        # if verify(passw, g.user['password']):
        update_user_password(g.user['id'], hash(passw))

    return render_template('profile.html')


@app.route('/<path:url>')
@private
def link(url=''):
    if len(request.args) > 0:
        url = url + '?' + urllib.parse.urlencode(request.args)
    if not url.startswith('http'):
        url = '//' + url

    o = urllib.parse.urlparse(url, 'http')
    # missing netloc - back to index
    if o.netloc == '':
        # ToDo: flash here
        return redirect(url_for('index'))

    create_link_for_user(urllib.parse.urlunparse(o), g.user['id'])
    return redirect(url_for('index'))


# --------
# Commands
# --------

@app.cli.command('initdb')
def initdb_command():
    init_db()
    print('Initialized the database.')


# -------
# Filters
# -------

def lremove(str, prefix):
    return str[len(prefix):] if str.startswith(prefix) else str


def timesince(date):
    diff = datetime.utcnow() - date

    if diff / timedelta(days=1) > 1:
        return date.strftime('%d.%m.%y %H:%M')

    seconds = diff / timedelta(seconds=1)
    # hours
    if seconds >= 60 * 60:
        return f"{seconds / 60 / 60:.0f}h ago"

    if seconds >= 60:
        return f"{seconds / 60:.0f}m ago"

    return f"{abs(seconds):.0f}s ago"


app.jinja_env.filters['lremove'] = lremove
app.jinja_env.filters['timesince'] = timesince
