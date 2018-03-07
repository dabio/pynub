import bcrypt
import os
import psycopg2
import psycopg2.extras
import re

from flask import Flask, request, render_template, g, session, \
    redirect, url_for
from functools import wraps
from urllib.parse import urlencode

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'super-secret-key')


SESSION_TOKEN = 'token'
EMAIL_RE = '.+@.+\..+'
MIN_PWD_LEN = 4

# User Feeback
SIGNIN_NO_ACCOUNT = 'Invalid Email or Password.'
SIGNIN_WRONG_PASS = 'Invalid Email or Password.'

REGISTER_ACCOUNT_EXISTS = (
    'Account already exists. Would you like to sign in instead?'
)
REGISTER_INVALID_EMAIL = 'Invalid Email.'
REGISTER_PWD_TOO_SHORT = 'Password is too short.'
REGISTER_PWD_DONT_MATCH = 'Passwords do not match.'

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
    cur = get_db().cursor()
    cur.execute(query, args)
    res = cur.fetchall()
    return (res[0] if res else None) if one else res


def modify_db(query, args=()):
    db = get_db()
    cur = db.cursor()
    cur.execute(query, args)
    res = cur.fetchone()
    db.commit()
    return res


def get_user_by_email(email):
    return query_db(
        'SELECT id, email, password, created_at FROM users WHERE email = %s',
        [email], one=True)


def get_user_by_token(token):
    return query_db((
        'SELECT u.id, u.email, u.created_at, l.active_at, l.token FROM users u'
        ' JOIN logins l ON u.id = l.user_id AND l.token = %s'
        ' LIMIT 1'), [token], one=True)


def create_user(email, password_hash):
    res = modify_db(
        'INSERT INTO users (email, password) VALUES (%s, %s) RETURNING id',
        [email, password_hash])
    return res['id']


def refresh_token(token):
    modify_db((
        'UPDATE logins SET active_at = now() WHERE token = %s'
        ' RETURNING active_at'), [token])


def add_token(user_id):
    res = modify_db(
        'INSERT INTO logins (user_id) VALUES (%s) RETURNING token',
        [user_id])
    return res['token']


def get_link(url):
    return query_db(
        'SELECT id FROM links WHERE url = %s LIMIT 1', [url], one=True)


def create_link(url):
    res = modify_db('INSERT INTO links (url) VALUES (%s) RETURNING id', [url])
    return res['id']


def get_link_for_user(link_id, user_id):
    return query_db((
        'SELECT created_at FROM user_links WHERE link_id = %s AND user_id = %s'
        ' LIMIT 1'), [link_id, user_id], one=True)


def create_link_for_user(url, user_id):
    link_id = get_link(url)
    if link_id is None:
        link_id = create_link(url)

    res = get_link_for_user(link_id, user_id)
    if res is None:
        res = modify_db((
            'INSERT INTO user_links (link_id, user_id) VALUES (%s, %s)'
            ' RETURNING created_at'), link_id, user_id)

    return res


# ----------
# Decorators
# ----------

def private(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            return redirect(url_for('signin', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def public(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is not None:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# -------
# Signals
# -------

@app.before_request
def preload_user():
    g.user = None
    if SESSION_TOKEN in session:
        g.user = get_user_by_token(session[SESSION_TOKEN])


@app.before_request
def prolong_session():
    session.permanent = True


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
        [g.user['id']]))


@app.route('/signin')
@public
def signin():
    return render_template('signin.html')


@app.route('/signin', methods=['POST'])
@public
def do_signin():
    user = get_user_by_email(request.form.get('email'))
    if user is None:
        return render_template('signin.html', error=SIGNIN_NO_ACCOUNT)

    if not bcrypt.checkpw(
            request.form.get('password').encode('utf-8'),
            user['password'].encode('utf-8')):
        return render_template('signin.html', error=SIGNIN_WRONG_PASS)

    session[SESSION_TOKEN] = add_token(user['id'])
    return redirect(url_for('index'))


@app.route('/register')
@public
def register():
    return render_template('register.html')


@app.route('/register', methods=['POST'])
@public
def do_register():
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

    hash_passw = bcrypt.hashpw(passw.encode('utf-8'), bcrypt.gensalt())

    session[SESSION_TOKEN] = add_token(create_user(email, hash_passw))
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


@app.route('/<path:url>')
@private
def link(url=''):
    if len(request.args) > 0:
        url += '?' + urlencode(request.args)
    return url


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


app.jinja_env.filters['lremove'] = lremove
