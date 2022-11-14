import apsw
import bcrypt
import click
import functools
import os
import re
import urllib.parse
import uuid

from datetime import datetime, timedelta
from flask import (
    Flask,
    request,
    render_template,
    g,
    session,
    redirect,
    url_for,
    flash,
    abort,
)


app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key")


SESSION_TOKEN = "token"
EMAIL_RE = ".+@.+\..+"
MIN_PWD_LEN = 4
DELETE_ME_COOKIE = "deleteMe"
IGNORE_ASSETS = (
    "apple-touch-icon-152x152-precomposed.png",
    "apple-touch-icon-152x152.png",
    "apple-touch-icon-120x120-precomposed.png",
    "apple-touch-icon-120x120.png",
    "apple-touch-icon-precomposed.png",
    "apple-touch-icon.png",
    "favicon.ico",
)

# User Feeback
SIGNIN_NO_ACCOUNT = "Invalid Email or Password."
SIGNIN_WRONG_PASS = "Invalid Email or Password."

REGISTER_INVALID_EMAIL = "Invalid Email."
REGISTER_PWD_TOO_SHORT = "Password is too short."
REGISTER_PWD_DONT_MATCH = "Passwords do not match."
REGISTER_ACCOUNT_EXISTS = "Account already exists. Would you like to sign in instead?"

LINKS_NEW_LINK = "Link added to your list."

PROFILE_INVALID_EMAIL = "Invalid Email."
PROFILE_WRONG_PASSWORD = "Password is not correct."
PROFILE_PWD_TOO_SHORT = "Password is too short."
PROFILE_ACCOUNT_EXISTS = "An account linked to this email exists already."
PROFILE_PWD_DONT_MATCH = "Passwords do not match."
PROFILE_SUCCESS_UPDATE = "User profile successfully updated."


# -------
# Helpers
# -------


def dict_row(cursor, row):
    return {k[0]: row[i] for i, k in enumerate(cursor.getdescription())}


def my_factory(connection):
    cursor = apsw.Cursor(connection)
    cursor.setrowtrace(dict_row)
    return cursor


def get_db():
    conn = apsw.Connection(os.getenv("DSN", "pinub.db"))
    conn.cursor_factory = my_factory
    return g.get("_db", conn)


def init_db():
    db = get_db()
    with app.open_resource("schema.sql", mode="r") as f:
        db.cursor().execute(f.read())
    db.commit()


def query_db(query, args=(), one=False):
    db = get_db()
    cur = db.cursor()
    cur.execute(query, args)
    # if query.lower().startswith(("insert ", "update ", "delete ")):
    # db.commit()
    if query.lower().startswith("delete "):
        return None
    return cur.fetchone() if one else cur.fetchall()


def get_user_by_email(email):
    return query_db(
        "SELECT id, email, password, created_at FROM users WHERE email = ?",
        (email,),
        one=True,
    )


def get_user_by_token(token):
    return query_db(
        (
            "SELECT id, email, password, u.created_at, active_at, token"
            " FROM users u JOIN logins l ON u.id = l.user_id AND l.token = ?"
            " LIMIT 1"
        ),
        (token,),
        one=True,
    )


def create_user(email, password_hash):
    res = query_db(
        "INSERT INTO users (email, password) VALUES (?, ?) RETURNING id",
        (email, password_hash),
        one=True,
    )
    return res["id"]


def update_user_password(user_id, password_hash):
    res = query_db(
        "UPDATE users SET password = ? WHERE id = ? RETURNING id",
        (password_hash, user_id),
        one=True,
    )
    return res["id"]


def update_user_email(user_id, email):
    res = query_db(
        "UPDATE users SET email = ? WHERE id = ? RETURNING id",
        (email, user_id),
        one=True,
    )
    return res


def refresh_token(token):
    query_db(
        "UPDATE logins SET active_at = datetime('now') WHERE token = ? RETURNING active_at",
        (token,),
    )


def add_token(user_id):
    res = query_db(
        "INSERT INTO logins (token, user_id) VALUES (?, ?) RETURNING token",
        (str(uuid.uuid4()), user_id),
        one=True,
    )
    return res["token"]


def get_link(url):
    return query_db("SELECT id FROM links WHERE url = ? LIMIT 1", (url,), one=True)


def create_link(url):
    res = query_db("INSERT INTO links (url) VALUES (?) RETURNING id", (url,), one=True)
    return res["id"]


def get_link_for_user(link_id, user_id):
    return query_db(
        (
            "SELECT created_at FROM user_links WHERE link_id = ? AND user_id = ?"
            " LIMIT 1"
        ),
        (link_id, user_id),
        one=True,
    )


def create_link_for_user(url, user_id):
    link = get_link(url)
    if link is None:
        link_id = create_link(url)
    else:
        link_id = link["id"]

    res = get_link_for_user(link_id, user_id)
    if res is None:
        res = query_db(
            (
                "INSERT INTO user_links (link_id, user_id) VALUES (?, ?)"
                " RETURNING created_at"
            ),
            (link_id, user_id),
            one=True,
        )

    return res


def delete_link_for_user(link_id, user_id):
    query_db(
        "DELETE FROM user_links WHERE user_id = ? AND link_id = ?", (user_id, link_id)
    )
    query_db(
        (
            "DELETE FROM links WHERE id = ? AND"
            " (SELECT count(link_id) FROM user_links WHERE link_id = ?) = 0"
        ),
        (link_id, link_id),
    )


def hash(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(10, b"2a")).decode(
        "utf-8"
    )


def verify(password, hash):
    return bcrypt.checkpw(password.encode("utf-8"), hash.encode("utf-8"))


# ----------
# Decorators
# ----------


def private(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("signin"))
        return f(*args, **kwargs)

    return decorated_function


def public(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is not None:
            return redirect(url_for("index"))
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

    links = cookie.split(",")
    for link_id in links:
        delete_link_for_user(link_id, g.user["id"])


@app.after_request
def show_processed_time(response):
    diff = (datetime.utcnow() - request.start_time).total_seconds()
    response.headers["X-Processed-Time"] = f"{diff * 1000:.2f}ms"
    return response


@app.teardown_request
def refresh_user_token(exception):
    if g.user is not None:
        refresh_token(g.user["token"])


@app.teardown_appcontext
def close_database(exception):
    if hasattr(g, "_db"):
        get_db().close()


# ------
# Routes
# ------


@app.route("/")
def index():
    if g.user is None:
        return render_template("home.html")
    return render_template(
        "links.html",
        links=query_db(
            (
                "SELECT id, url, ul.created_at FROM links l"
                " JOIN user_links ul ON l.id = ul.link_id AND ul.user_id = ?"
                " ORDER BY ul.created_at DESC"
            ),
            (g.user["id"],),
        ),
    )


@app.route("/signin")
@public
@functools.lru_cache(512)
def signin():
    return render_template("signin.html")


@app.route("/signin", methods=["POST"])
@public
def post_signin():
    user = get_user_by_email(request.form.get("email"))

    if user is None:
        return render_template("signin.html", error=SIGNIN_NO_ACCOUNT)

    if not verify(request.form.get("password"), user["password"]):
        return render_template("signin.html", error=SIGNIN_WRONG_PASS)

    session[SESSION_TOKEN] = add_token(user["id"])
    return redirect(url_for("index"))


@app.route("/register")
@functools.lru_cache(512)
@public
def register():
    return render_template("register.html")


@app.route("/register", methods=["POST"])
@public
def post_register():
    email = request.form.get("email")
    passw = request.form.get("password")

    user = get_user_by_email(email)
    if user is not None:
        return render_template("register.html", error=REGISTER_ACCOUNT_EXISTS)

    if re.search(EMAIL_RE, email) is None:
        return render_template("register.html", error=REGISTER_INVALID_EMAIL)

    if len(passw) < MIN_PWD_LEN:
        return render_template("register.html", error=REGISTER_PWD_TOO_SHORT)

    if passw != request.form.get("password_confirm"):
        return render_template("register.html", error=REGISTER_PWD_DONT_MATCH)

    session[SESSION_TOKEN] = add_token(create_user(email, hash(passw)))
    return redirect(url_for("index"))


@app.route("/signout")
@private
def signout():
    session.pop(SESSION_TOKEN, None)
    return redirect(url_for("index"))


@app.route("/profile")
@private
def profile():
    return render_template("profile.html")


@app.route("/profile", methods=["POST"])
@private
def post_profile():
    if not verify(request.form.get("password"), g.user["password"]):
        return render_template("profile.html", error=PROFILE_WRONG_PASSWORD)

    email = request.form.get("email")
    if re.search(EMAIL_RE, email) is None:
        return render_template("profile.html", error=PROFILE_INVALID_EMAIL)

    test_user = get_user_by_email(email)
    if test_user is not None and test_user["id"] != g.user["id"]:
        return render_template("profile.html", error=PROFILE_ACCOUNT_EXISTS)

    passw = request.form.get("new_password")
    if len(passw) > 0:
        if len(passw) < MIN_PWD_LEN:
            return render_template("profile.html", error=PROFILE_PWD_TOO_SHORT)

        if passw != request.form.get("confirm_password"):
            return render_template("profile.html", error=PROFILE_PWD_DONT_MATCH)

        update_user_password(g.user["id"], hash(passw))

    update_user_email(g.user["id"], email)
    flash(PROFILE_SUCCESS_UPDATE, "info")
    return redirect(url_for("profile"))


@app.route("/<path:url>")
@private
def link(url=""):
    # ignore asset files
    if url in IGNORE_ASSETS:
        abort(404)

    if len(request.args) > 0:
        url = url + "?" + urllib.parse.urlencode(request.args)
    if not url.startswith("http"):
        url = "//" + url

    o = urllib.parse.urlparse(url, "http")
    # missing netloc - back to index
    if o.netloc == "":
        # ToDo: flash here
        return redirect(url_for("index"))

    create_link_for_user(urllib.parse.urlunparse(o), g.user["id"])
    flash(LINKS_NEW_LINK, "info")
    return redirect(url_for("index"))


# --------
# Commands
# --------


@app.cli.command("initdb")
def initdb_command():
    init_db()
    print("Initialized the database.")


@app.cli.command("hash")
@click.argument("password")
def hash_command(password):
    print(hash(password))


# -------
# Filters
# -------


def lremove(str, prefix):
    return str[len(prefix) :] if str.startswith(prefix) else str


def timesince(date):
    if isinstance(date, str):
        date = datetime.strptime(date, "%Y-%m-%d %H:%M:%S")
    diff = datetime.utcnow() - date

    if diff / timedelta(days=1) > 1:
        return date.strftime("%d.%m.%y %H:%M")

    seconds = diff / timedelta(seconds=1)
    # hours
    if seconds >= 60 * 60:
        return f"{seconds / 60 / 60:.0f}h ago"

    if seconds >= 60:
        return f"{seconds / 60:.0f}m ago"

    return f"{abs(seconds):.0f}s ago"


app.jinja_env.filters["lremove"] = lremove
app.jinja_env.filters["timesince"] = timesince
