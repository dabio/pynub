import unittest
import pinub

REGISTER_TEST_EMAIL = 'test1@test.de'

LINK_TEST_URL = 'http://flask.pocoo.org/docs/0.12/'


class PinubTestCase(unittest.TestCase):

    # Hooks

    def setUp(self):
        pinub.app.testing = True
        self.app = pinub.app.test_client()

    # Helpers

    def login(self, email, password, follow_redirects=False):
        return self.app.post('/signin', data=dict(
            email=email,
            password=password
        ), follow_redirects=follow_redirects)

    def register(self, email, password, confirm, follow_redirects=False):
        return self.app.post('/register', data=dict(
            email=email,
            password=password,
            password_confirm=confirm
        ), follow_redirects=follow_redirects)

    def delete_user(self, email):
        with pinub.app.app_context():
            pinub.delete_db('DELETE FROM users WHERE email = %s', (email, ))

    # Tests

    def test_index(self):
        res = self.app.get('/')
        assert 200 == res.status_code

    def test_signin(self):
        res = self.app.get('/signin')
        assert 200 == res.status_code
        assert b'Sign In' in res.data

    def test_post_signin(self):
        # wrong email
        res = self.login('test', 'test')
        assert b'Invalid Email or Password' in res.data
        # missing login
        res = self.login('', 'test')
        assert b'Invalid Email or Password' in res.data
        # missing password
        res = self.login('test', '')
        assert b'Invalid Email or Password' in res.data
        # correct credentials
        res = self.login('test@test.de', 'test')
        assert 302 == res.status_code
        assert 'http://localhost/' == res.location

    def test_signout(self):
        res = self.login('test@test.de', 'test', True)
        assert 200 == res.status_code
        assert 'session=' in res.headers.get('Set-Cookie')
        assert b'Sign In' not in res.data
        res = self.app.get('/signout')
        assert 302 == res.status_code
        assert 'http://localhost/' == res.location
        res = self.app.get(res.location)
        assert 200 == res.status_code
        assert b'Your Links' not in res.data

    def test_register(self):
        res = self.register('test', 'test', 'test')
        assert b'Invalid Email' in res.data
        res = self.register('test@test', 'test', 'test')
        assert b'Invalid Email' in res.data
        res = self.register('test@test.de', 'test', 'test')
        assert b'Account already exists' in res.data
        res = self.register(REGISTER_TEST_EMAIL, '12', '12')
        assert b'Password is too short' in res.data
        res = self.register(REGISTER_TEST_EMAIL, '1234', '12')
        assert b'Passwords do not match' in res.data
        res = self.register(REGISTER_TEST_EMAIL, '1234', '1234')
        assert 302 == res.status_code
        assert 'http://localhost/' == res.location
        # not needed anymore
        self.delete_user(REGISTER_TEST_EMAIL)

    def test_profile(self):
        res = self.app.get('/profile')
        assert 302 == res.status_code

    def test_link(self):
        res = self.app.get('/https://example.com/')
        assert 302 == res.status_code
        self.register(REGISTER_TEST_EMAIL, '1234', '1234', True)
        res = self.app.get('/' + LINK_TEST_URL)
        assert 302 == res.status_code
        res = self.app.get('/')
        assert LINK_TEST_URL.encode() in res.data
        # not needed anymore
        self.delete_user(REGISTER_TEST_EMAIL)


class HelperTestCase(unittest.TestCase):

    def test_timesince(self):
        pass


if __name__ == '__main__':
    unittest.main()
