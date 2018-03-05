import bcrypt
import os
import psycopg2
import psycopg2.extras

from flask import Flask, request, render_template, g, session, \
    redirect, url_for
from functools import wraps
from urllib.parse import urlencode

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'super-secret-key')


SESSION_TOKEN = 'token'


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
def before_request():
    g.user = None
    if SESSION_TOKEN in session:
        g.user = query_db((
            'SELECT u.id, u.email, u.created_at, l.active_at FROM users u'
            ' JOIN logins l ON u.id = l.user_id AND l.token = %s'
            ' LIMIT 1'), [session[SESSION_TOKEN]], one=True)


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
    # session[SESSION_TOKEN] = '1f859354-015e-48b0-a335-135b59f6743d'
    return render_template('signin.html')


@app.route('/signin', methods=['POST'])
@public
def do_signin():
    errors = {}
    user = query_db(
        'SELECT id, email, password FROM users WHERE email = %s',
        [request.form.get('email')],
        one=True
    )
    if user is None:
        print('User not found')
        errors['email'] = 'Invalid Email or Password'
    elif not bcrypt.checkpw(request.form.get('password').encode('utf-8'), user['password'].encode('utf-8')):
        print('Password not correct')
        errors['email'] = 'Invalid Email or Password'
    else:
        print('Password and Email correct')
        db = get_db()
        cur = db.cursor()
        cur.execute(
            'INSERT INTO logins (user_id) VALUES (%s) RETURNING token',
            [user['id']],
        )
        res = cur.fetchone()
        db.commit()
        print(res['token'])
        session[SESSION_TOKEN] = res['token']
        return redirect(url_for('index'))
    return render_template('signin.html', errors=errors)


@app.route('/register')
@public
def register():
    return render_template('register.html')


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
