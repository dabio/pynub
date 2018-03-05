import unittest
import pinub


class PinubTestCase(unittest.TestCase):
    def setUp(self):
        pinub.app.testing = True
        self.app = pinub.app.test_client()

    def test_index(self):
        res = self.app.get('/')
        assert 200 == res.status_code

    def test_signin(self):
        res = self.app.get('/signin')
        assert 200 == res.status_code

    def test_signout(self):
        res = self.app.get('/signout')
        assert 302 == res.status_code

    def test_register(self):
        res = self.app.get('/register')
        assert 200 == res.status_code

    def test_profile(self):
        res = self.app.get('/profile')
        assert 302 == res.status_code

    def test_link(self):
        res = self.app.get('/https://example.com/')
        assert 302 == res.status_code

        # assert b'https://example.com/' in res.data
        # assert 200 == res.status_code
        # res = self.app.get('/https://example.com/test?test=data')
        # assert 200 == res.status_code
        # assert b'https://example.com/test?test=data' in res.data


if __name__ == '__main__':
    unittest.main()
