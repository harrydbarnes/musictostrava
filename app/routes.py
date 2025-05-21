from flask import render_template, redirect, request, session, url_for, flash
from app import app
from app.config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET
import requests
import urllib.parse
from datetime import datetime, timezone, timedelta

# Spotify OAuth Configuration
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"

# Strava OAuth Configuration
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"

@app.route('/')
def index():
    spotify_connected = 'spotify_access_token' in session
    strava_connected = 'strava_access_token' in session
    # The logout routes logout_spotify and logout_strava are not yet defined.
    # They will be needed for the disconnect buttons in index.html
    return render_template('index.html', 
                           spotify_connected=spotify_connected, 
                           strava_connected=strava_connected)

@app.route('/run_update', methods=['POST'])
def run_update():
    if 'spotify_access_token' not in session or 'strava_access_token' not in session:
        flash('Please connect both Spotify and Strava accounts.', 'error')
        return redirect(url_for('update_activity'))

    strava_token = session['strava_access_token']
    spotify_token = session['spotify_access_token']

    # 1. Fetch Latest Strava Activity
    try:
        strava_activities_url = "https://www.strava.com/api/v3/athlete/activities"
        headers_strava = {'Authorization': f'Bearer {strava_token}'}
        params_strava = {'per_page': 1, 'page': 1}
        
        response_strava = requests.get(strava_activities_url, headers=headers_strava, params=params_strava)
        response_strava.raise_for_status() # Raise HTTPError for bad responses (4XX or 5XX)
        latest_activities = response_strava.json()

        if not latest_activities:
            flash('No Strava activities found.', 'error')
            return redirect(url_for('update_activity'))

        latest_activity = latest_activities[0]
        activity_id = latest_activity['id']
        start_date_local_str = latest_activity['start_date_local']
        elapsed_time_seconds = latest_activity['elapsed_time']
        existing_description = latest_activity.get('description', "") # Description might be null

    except requests.exceptions.RequestException as e:
        flash(f'Error fetching Strava activity: {e}', 'error')
        return redirect(url_for('update_activity'))
    except (IndexError, KeyError) as e:
        flash(f'Error parsing Strava activity data: {e}', 'error')
        return redirect(url_for('update_activity'))

    # 2. Fetch Spotify History
    try:
        # Convert start_date_local (e.g., "2024-01-15T18:00:00Z") to Unix timestamp in milliseconds
        # Strava's start_date_local is not always timezone aware, and might not have 'Z'.
        # Assuming it's in local time as per its name. For robust solution, user's timezone might be needed.
        # For now, we parse it as ISO format. If it has 'Z', it's UTC. If not, Python 3.7+ fromisoformat handles it.
        # To be safe, let's ensure it is treated as UTC if 'Z' is present, otherwise assume local and convert to UTC.
        if start_date_local_str.endswith('Z'):
            start_datetime_utc = datetime.fromisoformat(start_date_local_str[:-1] + '+00:00')
        else:
            # This is tricky. 'start_date_local' means it's local to where the activity was recorded.
            # For simplicity, if no timezone info, we'll assume it's naive and then treat it as UTC for Spotify.
            # A better approach would be to get the activity's timezone if available or use user's configured timezone.
            # For now, parse and assume it's meant to be UTC for the purpose of time window.
            start_datetime_naive = datetime.fromisoformat(start_date_local_str)
            start_datetime_utc = start_datetime_naive.replace(tzinfo=timezone.utc) # Treat as UTC

        start_timestamp_ms = int(start_datetime_utc.timestamp() * 1000)
        
        # Calculate 'before' timestamp
        end_datetime_utc = start_datetime_utc + timedelta(seconds=elapsed_time_seconds)
        end_timestamp_ms = int(end_datetime_utc.timestamp() * 1000)

        spotify_history_url = "https://api.spotify.com/v1/me/player/recently-played"
        headers_spotify = {'Authorization': f'Bearer {spotify_token}'}
        params_spotify = {'limit': 50, 'after': start_timestamp_ms, 'before': end_timestamp_ms}

        response_spotify = requests.get(spotify_history_url, headers=headers_spotify, params=params_spotify)
        response_spotify.raise_for_status()
        spotify_history = response_spotify.json()

        if not spotify_history.get('items'):
            flash('No Spotify listening history found for the duration of your latest Strava activity.', 'info')
            return redirect(url_for('update_activity'))

    except requests.exceptions.RequestException as e:
        flash(f'Error fetching Spotify history: {e}', 'error')
        return redirect(url_for('update_activity'))
    except Exception as e: # Catch other potential errors like timestamp conversion
        flash(f'An error occurred preparing Spotify request: {e}', 'error')
        return redirect(url_for('update_activity'))

    # 3. Filter and Format Songs
    songs_list = []
    for item in spotify_history.get('items', []):
        track = item.get('track')
        if track:
            song_name = track.get('name')
            artists = ", ".join([artist.get('name') for artist in track.get('artists', []) if artist.get('name')])
            if song_name and artists:
                songs_list.append(f"{song_name} - {artists}")
    
    if not songs_list:
        flash('No songs with track and artist information found in the Spotify history for this period.', 'info')
        return redirect(url_for('update_activity'))

    # Remove duplicates while preserving order for the final list
    unique_songs = []
    seen_songs = set()
    for song in songs_list:
        if song not in seen_songs:
            unique_songs.append(song)
            seen_songs.add(song)
            
    formatted_songs = "\n".join([f"{idx + 1}. {song}" for idx, song in enumerate(unique_songs)])

    # 4. Update Strava Activity Description
    try:
        new_description = f"{existing_description}\n\n🎵 Songs from this activity:\n{formatted_songs}".strip()
        
        strava_update_url = f"https://www.strava.com/api/v3/activities/{activity_id}"
        payload_strava_update = {'description': new_description}
        
        response_update_strava = requests.put(strava_update_url, headers=headers_strava, json=payload_strava_update)
        response_update_strava.raise_for_status()

        flash(f'Strava activity description updated with {len(unique_songs)} songs!', 'success')

    except requests.exceptions.RequestException as e:
        flash(f'Error updating Strava activity: {e}. Response: {response_update_strava.text}', 'error')
    except Exception as e:
        flash(f'An unexpected error occurred during Strava update: {e}', 'error')
        
    return redirect(url_for('update_activity'))

@app.route('/login/spotify')
def login_spotify():
    # We need to define SPOTIFY_REDIRECT_URI first.
    # This will be done after spotify_callback is defined.
    # For now, let's use a placeholder.
    # This will be updated once spotify_callback is defined.
    redirect_uri = url_for('spotify_callback', _external=True)
    
    params = {
        'client_id': SPOTIFY_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'scope': 'user-read-recently-played',
    }
    auth_url = f"{SPOTIFY_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return redirect(auth_url)

@app.route('/callback/spotify')
def spotify_callback():
    error = request.args.get('error')
    if error:
        return f"Error received from Spotify: {error}", 400

    code = request.args.get('code')
    if not code:
        return "No code received from Spotify.", 400

    redirect_uri = url_for('spotify_callback', _external=True)

    payload = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
    }
    
    response = requests.post(
        SPOTIFY_TOKEN_URL,
        data=payload,
        auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
    )
    
    token_info = response.json()
    
    if response.status_code != 200:
        return f"Error getting token from Spotify: {token_info.get('error_description', 'Unknown error')}", 400

    session['spotify_access_token'] = token_info.get('access_token')
    session['spotify_refresh_token'] = token_info.get('refresh_token')
    
    return redirect(url_for('index'))

@app.route('/login/strava')
def login_strava():
    redirect_uri = url_for('strava_callback', _external=True)
    params = {
        'client_id': STRAVA_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'approval_prompt': 'force',
        'scope': 'activity:read_latest,activity:write'
    }
    auth_url = f"{STRAVA_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return redirect(auth_url)

@app.route('/callback/strava')
def strava_callback():
    error = request.args.get('error')
    if error:
        return f"Error received from Strava: {error}", 400

    code = request.args.get('code')
    if not code:
        return "No code received from Strava.", 400

    redirect_uri = url_for('strava_callback', _external=True) # Though not strictly needed by Strava token exchange

    payload = {
        'client_id': STRAVA_CLIENT_ID,
        'client_secret': STRAVA_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code'
    }
    
    response = requests.post(STRAVA_TOKEN_URL, data=payload)
    token_info = response.json()

    if response.status_code != 200:
        return f"Error getting token from Strava: {token_info.get('message', 'Unknown error')}", 400
        
    session['strava_access_token'] = token_info.get('access_token')
    session['strava_refresh_token'] = token_info.get('refresh_token')
    
    # Strava also returns athlete info in the token response, which can be stored if needed
    # session['strava_athlete'] = token_info.get('athlete')

    return redirect(url_for('index'))

@app.route('/update_activity')
def update_activity():
    spotify_connected = 'spotify_access_token' in session
    strava_connected = 'strava_access_token' in session
    
    # The route for the form action, /run_update, will be created in a future task.
    # For now, the template update_activity.html references url_for('run_update')
    # which will cause a werkzeug.routing.exceptions.BuildError if not defined.
    # To prevent this, we can pass a dummy value or ensure run_update is defined,
    # even if it's just a placeholder. For now, I'll assume run_update will be
    # defined later as per the overall project plan.
    
    return render_template('update_activity.html', 
                           spotify_connected=spotify_connected, 
                           strava_connected=strava_connected)
