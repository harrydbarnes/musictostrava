import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the parent directory to the Python path to allow importing 'app'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from app.routes import SPOTIFY_AUTH_URL, STRAVA_AUTH_URL # Import constants for checking redirects

class FlaskAppTests(unittest.TestCase):

    def setUp(self):
        """Set up test client and configure app for testing."""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for testing forms if any
        app.config['SECRET_KEY'] = 'test_secret_key_for_sessions'
        # Set dummy client IDs and secrets for testing purposes
        # These are needed because routes.py imports them at module level.
        app.config['SPOTIFY_CLIENT_ID'] = 'test_spotify_client_id'
        app.config['SPOTIFY_CLIENT_SECRET'] = 'test_spotify_client_secret'
        app.config['STRAVA_CLIENT_ID'] = 'test_strava_client_id'
        app.config['STRAVA_CLIENT_SECRET'] = 'test_strava_client_secret'
        self.client = app.test_client()

    def tearDown(self):
        """Clean up after each test."""
        pass # Nothing specific to clean up yet

    # Test Cases for Authentication Redirects
    def test_login_spotify_redirects(self):
        """Test that /login/spotify redirects to the Spotify auth URL."""
        response = self.client.get('/login/spotify')
        self.assertEqual(response.status_code, 302) # Check for redirect
        self.assertTrue(response.location.startswith(SPOTIFY_AUTH_URL))
        # Check for required query parameters
        self.assertIn('client_id=' + app.config['SPOTIFY_CLIENT_ID'], response.location)
        self.assertIn('response_type=code', response.location)
        self.assertIn('scope=user-read-recently-played', response.location)
        self.assertIn('redirect_uri=', response.location)

    def test_login_strava_redirects(self):
        """Test that /login/strava redirects to the Strava auth URL."""
        response = self.client.get('/login/strava')
        self.assertEqual(response.status_code, 302) # Check for redirect
        self.assertTrue(response.location.startswith(STRAVA_AUTH_URL))
        # Check for required query parameters
        self.assertIn('client_id=' + app.config['STRAVA_CLIENT_ID'], response.location)
        self.assertIn('response_type=code', response.location)
        self.assertIn('scope=activity:read_latest,activity:write', response.location)
        self.assertIn('approval_prompt=force', response.location)
        self.assertIn('redirect_uri=', response.location)

    # Test Cases for Callback Logic (Simplified - focus on session)
    @patch('app.routes.requests.post')
    def test_spotify_callback_sets_session(self, mock_post):
        """Test /callback/spotify sets session variables correctly."""
        # Mock the response from Spotify's token endpoint
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'mock_spotify_access_token',
            'refresh_token': 'mock_spotify_refresh_token',
            'expires_in': 3600
        }
        mock_post.return_value = mock_response

        # Simulate the callback from Spotify with a code
        response = self.client.get('/callback/spotify?code=test_code')
        
        self.assertEqual(response.status_code, 302) # Should redirect to index
        self.assertEqual(response.location, '/index') # or url_for('index')
        
        with self.client.session_transaction() as sess:
            self.assertIn('spotify_access_token', sess)
            self.assertEqual(sess['spotify_access_token'], 'mock_spotify_access_token')
            self.assertIn('spotify_refresh_token', sess)
            self.assertEqual(sess['spotify_refresh_token'], 'mock_spotify_refresh_token')

    @patch('app.routes.requests.post')
    def test_strava_callback_sets_session(self, mock_post):
        """Test /callback/strava sets session variables correctly."""
        # Mock the response from Strava's token endpoint
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'access_token': 'mock_strava_access_token',
            'refresh_token': 'mock_strava_refresh_token',
            'athlete': {'id': 12345} # Strava often returns athlete info
        }
        mock_post.return_value = mock_response

        # Simulate the callback from Strava with a code
        response = self.client.get('/callback/strava?code=test_code')

        self.assertEqual(response.status_code, 302) # Should redirect to index
        self.assertEqual(response.location, '/index')

        with self.client.session_transaction() as sess:
            self.assertIn('strava_access_token', sess)
            self.assertEqual(sess['strava_access_token'], 'mock_strava_access_token')
            self.assertIn('strava_refresh_token', sess)
            self.assertEqual(sess['strava_refresh_token'], 'mock_strava_refresh_token')
            # self.assertIn('strava_athlete', sess) # If you store this

    # Test Cases for /update_activity Page
    def test_update_activity_page_renders(self):
        """Test that /update_activity renders the correct template."""
        response = self.client.get('/update_activity')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Update Strava Activity', response.data) # Check for a known string in the template

    def test_update_activity_status_connected(self):
        """Test /update_activity shows connected status if tokens are in session."""
        with self.client.session_transaction() as sess:
            sess['spotify_access_token'] = 'fake_spotify_token'
            sess['strava_access_token'] = 'fake_strava_token'
        
        response = self.client.get('/update_activity')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Spotify: <span class="status-connected">Connected</span>', response.data)
        self.assertIn(b'Strava: <span class="status-connected">Connected</span>', response.data)
        self.assertIn(b'Update Latest Strava Activity</button>', response.data) # Button should be visible

    def test_update_activity_status_not_connected_spotify(self):
        """Test /update_activity shows not connected for Spotify if token is missing."""
        with self.client.session_transaction() as sess:
            # sess['spotify_access_token'] = 'fake_spotify_token' # Spotify missing
            sess['strava_access_token'] = 'fake_strava_token'
        
        response = self.client.get('/update_activity')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Spotify: <span class="status-not-connected">Not Connected</span>', response.data)
        self.assertIn(b'Strava: <span class="status-connected">Connected</span>', response.data)
        self.assertNotIn(b'Update Latest Strava Activity</button>', response.data) # Button should NOT be visible

    def test_update_activity_status_not_connected_strava(self):
        """Test /update_activity shows not connected for Strava if token is missing."""
        with self.client.session_transaction() as sess:
            sess['spotify_access_token'] = 'fake_spotify_token'
            # sess['strava_access_token'] = 'fake_strava_token' # Strava missing
        
        response = self.client.get('/update_activity')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Spotify: <span class="status-connected">Connected</span>', response.data)
        self.assertIn(b'Strava: <span class="status-not-connected">Not Connected</span>', response.data)
        self.assertNotIn(b'Update Latest Strava Activity</button>', response.data) # Button should NOT be visible

    def test_update_activity_status_not_connected_both(self):
        """Test /update_activity shows not connected for both if tokens are missing."""
        # No session modification needed, default is no tokens
        response = self.client.get('/update_activity')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Spotify: <span class="status-not-connected">Not Connected</span>', response.data)
        self.assertIn(b'Strava: <span class="status-not-connected">Not Connected</span>', response.data)
        self.assertNotIn(b'Update Latest Strava Activity</button>', response.data) # Button should NOT be visible

    # Test Cases for /run_update Logic
    def test_run_update_no_tokens(self):
        """Test /run_update redirects and flashes error if tokens are missing."""
        response = self.client.post('/run_update') # POST request
        self.assertEqual(response.status_code, 302) # Redirect
        self.assertEqual(response.location, '/update_activity') # Redirect to update_activity
        
        # Check for flash message
        # To check flash messages, we need to follow the redirect and inspect the response
        # Or, we can check the session for the flashed message if not following redirect
        with self.client.session_transaction() as sess:
            flashes = sess.get('_flashes', [])
            self.assertTrue(any('Please connect both Spotify and Strava accounts.' in message[1] for message in flashes))

    @patch('app.routes.requests.put') # Mock for Strava update
    @patch('app.routes.requests.get') # Mock for Strava activities and Spotify history
    def test_run_update_successful(self, mock_get, mock_put):
        """Test a successful run of /run_update."""
        # Setup session with tokens
        with self.client.session_transaction() as sess:
            sess['spotify_access_token'] = 'mock_spotify_token'
            sess['strava_access_token'] = 'mock_strava_token'

        # Mock responses for API calls
        mock_strava_activity_response = MagicMock()
        mock_strava_activity_response.status_code = 200
        mock_strava_activity_response.json.return_value = [{
            'id': 12345,
            'start_date_local': '2024-01-01T10:00:00Z',
            'elapsed_time': 3600, # 1 hour
            'description': 'Morning Run'
        }]

        mock_spotify_history_response = MagicMock()
        mock_spotify_history_response.status_code = 200
        mock_spotify_history_response.json.return_value = {
            'items': [
                {'track': {'name': 'Song A', 'artists': [{'name': 'Artist 1'}]}},
                {'track': {'name': 'Song B', 'artists': [{'name': 'Artist 2'}]}},
                {'track': {'name': 'Song A', 'artists': [{'name': 'Artist 1'}]}}, # Duplicate
            ]
        }
        
        mock_strava_update_response = MagicMock()
        mock_strava_update_response.status_code = 200
        mock_strava_update_response.json.return_value = {'id': 12345, 'description': 'Updated!'}

        # Configure side_effect for mock_get based on URL
        def get_side_effect(url, headers=None, params=None, **kwargs):
            if "strava.com/api/v3/athlete/activities" in url:
                return mock_strava_activity_response
            elif "api.spotify.com/v1/me/player/recently-played" in url:
                # Basic check for 'after' and 'before' params if needed for more rigorous test
                self.assertIn('after', params)
                self.assertIn('before', params)
                self.assertTrue(isinstance(params['after'], int))
                self.assertTrue(isinstance(params['before'], int))
                return mock_spotify_history_response
            return MagicMock(status_code=404) # Should not happen
        
        mock_get.side_effect = get_side_effect
        mock_put.return_value = mock_strava_update_response

        response = self.client.post('/run_update')
        self.assertEqual(response.status_code, 302) # Redirect to update_activity
        self.assertEqual(response.location, '/update_activity')

        # Verify Strava update payload
        mock_put.assert_called_once()
        args, kwargs = mock_put.call_args
        self.assertTrue(args[0].startswith("https://www.strava.com/api/v3/activities/"))
        updated_description = kwargs['json']['description']
        self.assertIn("Morning Run", updated_description) # Original description
        self.assertIn("🎵 Songs from this activity:", updated_description)
        self.assertIn("1. Song A - Artist 1", updated_description)
        self.assertIn("2. Song B - Artist 2", updated_description)
        self.assertNotIn("Song A - Artist 1\n2. Song A - Artist 1", updated_description) # Check duplicate removal

        # Check for success flash message
        res_follow = self.client.get(response.location) # Follow redirect
        self.assertIn(b'Strava activity description updated with 2 songs!', res_follow.data)


    @patch('app.routes.requests.get')
    def test_run_update_no_strava_activity(self, mock_get):
        """Test /run_update when no Strava activity is found."""
        with self.client.session_transaction() as sess:
            sess['spotify_access_token'] = 'mock_spotify_token'
            sess['strava_access_token'] = 'mock_strava_token'

        mock_strava_activity_response = MagicMock()
        mock_strava_activity_response.status_code = 200
        mock_strava_activity_response.json.return_value = [] # No activities
        mock_get.return_value = mock_strava_activity_response # Only Strava activities call mocked

        response = self.client.post('/run_update')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/update_activity')
        
        res_follow = self.client.get(response.location)
        self.assertIn(b'No Strava activities found.', res_follow.data)

    @patch('app.routes.requests.put') # Mock for Strava update (should not be called)
    @patch('app.routes.requests.get') # Mock for Strava activities and Spotify history
    def test_run_update_no_spotify_songs(self, mock_get, mock_put):
        """Test /run_update when no Spotify songs are found in the time range."""
        with self.client.session_transaction() as sess:
            sess['spotify_access_token'] = 'mock_spotify_token'
            sess['strava_access_token'] = 'mock_strava_token'

        mock_strava_activity_response = MagicMock()
        mock_strava_activity_response.status_code = 200
        mock_strava_activity_response.json.return_value = [{
            'id': 12345, 'start_date_local': '2024-01-01T10:00:00Z', 'elapsed_time': 3600, 'description': 'Morning Run'
        }]
        
        mock_spotify_history_response = MagicMock()
        mock_spotify_history_response.status_code = 200
        mock_spotify_history_response.json.return_value = {'items': []} # No songs

        mock_get.side_effect = [mock_strava_activity_response, mock_spotify_history_response]

        response = self.client.post('/run_update')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/update_activity')
        
        res_follow = self.client.get(response.location)
        self.assertIn(b'No Spotify listening history found for the duration', res_follow.data)
        mock_put.assert_not_called() # Strava update should not be called

    @patch('app.routes.requests.put')
    @patch('app.routes.requests.get')
    def test_run_update_spotify_api_error(self, mock_get, mock_put):
        """Test /run_update when Spotify API returns an error."""
        with self.client.session_transaction() as sess:
            sess['spotify_access_token'] = 'mock_spotify_token'
            sess['strava_access_token'] = 'mock_strava_token'

        mock_strava_activity_response = MagicMock()
        mock_strava_activity_response.status_code = 200
        mock_strava_activity_response.json.return_value = [{
            'id': 12345, 'start_date_local': '2024-01-01T10:00:00Z', 'elapsed_time': 3600, 'description': 'Morning Run'
        }]
        
        mock_spotify_error_response = MagicMock()
        mock_spotify_error_response.status_code = 403 # Forbidden or other error
        mock_spotify_error_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Spotify API Error")
        mock_spotify_error_response.json.return_value = {'error': {'message': 'Rate limit exceeded or auth error'}}


        mock_get.side_effect = [mock_strava_activity_response, mock_spotify_error_response]

        response = self.client.post('/run_update')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/update_activity')
        
        res_follow = self.client.get(response.location)
        self.assertIn(b'Error fetching Spotify history:', res_follow.data)
        mock_put.assert_not_called()

    @patch('app.routes.requests.put')
    @patch('app.routes.requests.get')
    def test_run_update_strava_api_error_on_update(self, mock_get, mock_put):
        """Test /run_update when Strava API returns an error during activity update."""
        with self.client.session_transaction() as sess:
            sess['spotify_access_token'] = 'mock_spotify_token'
            sess['strava_access_token'] = 'mock_strava_token'

        mock_strava_activity_response = MagicMock()
        mock_strava_activity_response.status_code = 200
        mock_strava_activity_response.json.return_value = [{
            'id': 12345, 'start_date_local': '2024-01-01T10:00:00Z', 'elapsed_time': 3600, 'description': 'Morning Run'
        }]
        
        mock_spotify_history_response = MagicMock()
        mock_spotify_history_response.status_code = 200
        mock_spotify_history_response.json.return_value = {
            'items': [{'track': {'name': 'Song A', 'artists': [{'name': 'Artist 1'}]}}]
        }
        mock_get.side_effect = [mock_strava_activity_response, mock_spotify_history_response]
        
        mock_strava_update_error_response = MagicMock()
        mock_strava_update_error_response.status_code = 500 # Server error
        mock_strava_update_error_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Strava Update Error")
        mock_strava_update_error_response.text = "Internal Server Error from Strava" # For error message
        mock_put.return_value = mock_strava_update_error_response


        response = self.client.post('/run_update')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/update_activity')
        
        res_follow = self.client.get(response.location)
        self.assertIn(b'Error updating Strava activity:', res_follow.data)
        self.assertIn(b'Internal Server Error from Strava', res_follow.data) # Check if response text is included in flash

if __name__ == '__main__':
    # This allows running the tests directly from this file
    # For discovery, use: python -m unittest discover -s tests
    unittest.main()
