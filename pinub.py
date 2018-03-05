import os
import psycopg2

from psycopg2.extras import DictCursor
from flask import Flask, request, render_template, g, session, \
    redirect, url_for
from urllib.parse import urlencode

app = Flask(__name__)
app.secret_key = os.environ['FLASK_SECRET_KEY']


SESSION_TOKEN = 'token'


# -------
# Helpers
# -------


def get_db():
    return g.get('pg_conn', psycopg2.connect(os.environ['DATABASE_URL']))


def get_cur():
    return g.get('pg_cur', get_db().cursor(cursor_factory=DictCursor))


def init_db():
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().execute(f.read())
    db.commit()


def query_db(query, args=(), one=False):
    db = get_cur()
    db.execute(query, args)
    res = db.fetchall()
    return (res[0] if res else None) if one else res


# --------
# Commands
# --------

@app.cli.command('initdb')
def initdb_command():
    init_db()
    print('Initialized the database.')


# -------
# Signals
# -------

@app.before_request
def before_request():
    g.user = None
    if SESSION_TOKEN in session:
        g.user = query_db((
            'SELECT u.id, u.email, u.created_at FROM users u'
            ' JOIN logins l ON u.id = l.user_id AND l.token = %s'
            ' LIMIT 1'), [session[SESSION_TOKEN]], one=True)


@app.teardown_appcontext
def close_database(exception):
    if hasattr(g, 'pg_cur'):
        get_cur().close()
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
def signin():
    session[SESSION_TOKEN] = '3f4c5dd7-8f4a-437c-95e8-b7e7a5680b62'
    return render_template('signin.html')


@app.route('/signout')
def signout():
    session.pop('user', None)
    return redirect(url_for('index'))


@app.route('/register')
def register():
    return render_template('register.html')


@app.route('/profile')
def profile():
    return render_template('profile.html')


@app.route('/<path:url>')
def link(url=''):
    if len(request.args) > 0:
        url += '?' + urlencode(request.args)
    return url
