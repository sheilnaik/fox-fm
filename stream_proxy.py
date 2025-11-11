#!/usr/bin/env python3
"""
Fox FM Radio Stream Proxy
Proxies the 101.9 Fox FM Melbourne HLS stream and provides a local M3U playlist
"""

import os
import logging
import re
import time
from urllib.parse import urljoin, urlparse
from flask import Flask, Response, request, stream_with_context
from flask_cors import CORS
from threading import Lock
import requests

# Configuration
PORT = int(os.getenv('PORT', 8000))
HOST = os.getenv('HOST', '0.0.0.0')
STREAM_URL = os.getenv('STREAM_URL', 'https://sa46.scastream.com.au/live/3fox_128.stream/playlist.m3u8')
STATION_NAME = os.getenv('STATION_NAME', '101.9 Fox FM Melbourne')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Default headers for requests
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': '*/*'
}

# Session cache to maintain valid stream sessions
# Maps stream URL -> session_url
# Sessions don't expire - they work indefinitely just like VLC
session_cache = {}
session_cache_lock = Lock()


def get_base_url():
    """Get the base URL for this proxy server"""
    if request.headers.get('X-Forwarded-Proto'):
        scheme = request.headers.get('X-Forwarded-Proto')
    else:
        scheme = request.scheme

    if request.headers.get('X-Forwarded-Host'):
        host = request.headers.get('X-Forwarded-Host')
    else:
        host = request.host

    return f"{scheme}://{host}"


@app.route('/stream.m3u')
def serve_m3u():
    """Serve the main M3U playlist file (HLS version)"""
    logger.info("Serving M3U playlist")

    base_url = get_base_url()

    # Try to get current track info
    current_track = "Live Stream"
    try:
        session_url = get_valid_session_url(STREAM_URL)
        response = requests.get(session_url, headers=DEFAULT_HEADERS, timeout=5)
        for line in response.text.split('\n'):
            if line.startswith('#EXTINF:') and 'title=' in line and 'artist=' in line:
                if 'Asset' not in line:
                    title_match = re.search(r'title="([^"]+)"', line)
                    artist_match = re.search(r'artist="([^"]+)"', line)
                    if title_match and artist_match:
                        current_track = f"{artist_match.group(1)} - {title_match.group(1)}"
                        break
    except:
        pass

    m3u_content = f"""#EXTM3U
#EXTINF:-1 tvg-logo="" radio="true",{STATION_NAME} - {current_track}
{base_url}/playlist.m3u8
"""

    return Response(m3u_content, mimetype='audio/x-mpegurl')


@app.route('/stream-icecast.m3u')
def serve_icecast_m3u():
    """Serve M3U playlist file pointing to Icecast stream (for TuneIn, etc.)"""
    logger.info("Serving Icecast M3U playlist")

    base_url = get_base_url()
    m3u_content = f"""#EXTM3U
#EXTINF:-1,{STATION_NAME}
{base_url}/icecast
"""

    return Response(m3u_content, mimetype='audio/x-mpegurl')


@app.route('/icecast')
def icecast_stream():
    """
    Serve a continuous ICY/Icecast-compatible stream with metadata
    This converts the HLS stream to a continuous stream for apps like TuneIn
    """
    logger.info("Client connected to Icecast stream")

    # Check if client supports ICY metadata
    icy_metadata = request.headers.get('Icy-MetaData', '0') == '1'

    def generate_stream():
        """Generator that continuously fetches HLS segments and streams them"""
        last_metadata = None
        metaint = 16000  # Send metadata every 16KB (standard for Icecast)
        byte_count = 0

        while True:
            try:
                # Get current session URL
                session_url = get_valid_session_url(STREAM_URL)

                # Fetch the media playlist
                response = requests.get(session_url, headers=DEFAULT_HEADERS, timeout=10)
                response.raise_for_status()

                playlist_content = response.text

                # Extract metadata from playlist
                current_metadata = None
                for line in playlist_content.split('\n'):
                    if line.startswith('#EXTINF:') and 'title=' in line and 'artist=' in line:
                        if 'Asset' not in line:
                            title_match = re.search(r'title="([^"]+)"', line)
                            artist_match = re.search(r'artist="([^"]+)"', line)
                            if title_match and artist_match:
                                title = title_match.group(1)
                                artist = artist_match.group(1)
                                current_metadata = f"{artist} - {title}"
                                break

                if not current_metadata:
                    current_metadata = f"{STATION_NAME} - Live Stream"

                # Get segment URLs from playlist
                segment_urls = []
                stream_base_url = session_url.rsplit('/', 1)[0] + '/'

                for line in playlist_content.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('#') and '.aac' in line:
                        if line.startswith('http'):
                            segment_urls.append(line)
                        else:
                            segment_urls.append(urljoin(stream_base_url, line))

                # Stream each segment
                for segment_url in segment_urls:
                    try:
                        seg_response = requests.get(segment_url, headers=DEFAULT_HEADERS, stream=True, timeout=10)
                        seg_response.raise_for_status()

                        # Stream the segment in chunks
                        for chunk in seg_response.iter_content(chunk_size=8192):
                            if chunk:
                                # If ICY metadata is supported, inject metadata every metaint bytes
                                if icy_metadata:
                                    chunk_pos = 0
                                    while chunk_pos < len(chunk):
                                        # Calculate how many bytes until next metadata
                                        bytes_until_meta = metaint - byte_count

                                        if bytes_until_meta <= len(chunk) - chunk_pos:
                                            # Send audio data up to metadata point
                                            yield chunk[chunk_pos:chunk_pos + bytes_until_meta]
                                            chunk_pos += bytes_until_meta
                                            byte_count = 0

                                            # Send metadata if it changed
                                            if current_metadata != last_metadata:
                                                last_metadata = current_metadata

                                            # Format ICY metadata
                                            meta_str = f"StreamTitle='{current_metadata}';"
                                            meta_len = len(meta_str)
                                            # Metadata length is sent as length/16
                                            meta_len_byte = bytes([meta_len // 16 + (1 if meta_len % 16 else 0)])
                                            # Pad metadata to multiple of 16 bytes
                                            padding = (16 - (meta_len % 16)) % 16
                                            meta_data = meta_str.encode('utf-8') + (b'\x00' * padding)

                                            yield meta_len_byte + meta_data
                                        else:
                                            # Send rest of chunk
                                            yield chunk[chunk_pos:]
                                            byte_count += len(chunk) - chunk_pos
                                            break
                                else:
                                    # No ICY metadata, just send the chunk
                                    yield chunk

                    except requests.RequestException as e:
                        logger.error(f"Error fetching segment {segment_url}: {e}")
                        continue

                # Small delay before fetching next playlist
                time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error in Icecast stream: {e}")
                time.sleep(1)

    # Build response headers
    headers = {
        'Content-Type': 'audio/aac',
        'Cache-Control': 'no-cache',
        'Connection': 'close',
        'icy-name': STATION_NAME,
        'icy-genre': 'Pop',
        'icy-url': get_base_url(),
        'icy-br': '128',
        'icy-pub': '1',
        'Access-Control-Allow-Origin': '*'
    }

    if icy_metadata:
        headers['icy-metaint'] = '16000'

    return Response(
        stream_with_context(generate_stream()),
        headers=headers,
        direct_passthrough=True
    )


def get_valid_session_url(base_stream_url):
    """Get or create a valid session URL for the stream"""
    global session_cache

    with session_cache_lock:
        # Check if we have a cached session
        if base_stream_url in session_cache:
            logger.debug(f"Using cached session")
            return session_cache[base_stream_url]

        # Need to get a fresh session (first time only)
        logger.info(f"Fetching initial session from: {base_stream_url}")
        response = requests.get(base_stream_url, headers=DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()

        # Extract the variant playlist URL with session ID
        for line in response.text.split('\n'):
            line = line.strip()
            if line and not line.startswith('#') and '.m3u8' in line:
                # This is the variant playlist URL with session
                session_url = line if line.startswith('http') else urljoin(base_stream_url, line)
                logger.info(f"Cached new session URL (will reuse indefinitely): {session_url}")
                session_cache[base_stream_url] = session_url
                return session_url

        # Fallback
        return base_stream_url

@app.route('/playlist.m3u8')
def proxy_playlist():
    """Proxy the HLS master playlist and rewrite URLs"""
    logger.info(f"Fetching playlist from: {STREAM_URL}")

    try:
        # Get a valid session URL (cached or fresh)
        session_url = get_valid_session_url(STREAM_URL)

        # Now fetch the actual media playlist using the session URL
        try:
            response = requests.get(session_url, headers=DEFAULT_HEADERS, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            # Session might be dead - invalidate cache and try once more
            logger.warning(f"Session request failed ({e}), refreshing session")
            with session_cache_lock:
                if STREAM_URL in session_cache:
                    del session_cache[STREAM_URL]
            session_url = get_valid_session_url(STREAM_URL)
            response = requests.get(session_url, headers=DEFAULT_HEADERS, timeout=10)
            response.raise_for_status()

        # Parse the base URL from the stream
        stream_base_url = session_url.rsplit('/', 1)[0] + '/'

        # Rewrite the playlist to proxy through our server
        playlist_content = response.text
        base_url = get_base_url()

        # Check if we got actual media segments or another redirect
        has_media_segments = False
        for line in playlist_content.split('\n'):
            if line.strip() and not line.startswith('#') and '.aac' in line:
                has_media_segments = True
                break

        if not has_media_segments and '#EXT-X-STREAM-INF' in playlist_content:
            # We got another variant playlist (session might be stale), invalidate cache and try once more
            logger.warning("Got variant playlist instead of media playlist, refreshing session")
            with session_cache_lock:
                if STREAM_URL in session_cache:
                    del session_cache[STREAM_URL]
            # Recursive call to get fresh session
            session_url = get_valid_session_url(STREAM_URL)
            response = requests.get(session_url, headers=DEFAULT_HEADERS, timeout=10)
            response.raise_for_status()
            playlist_content = response.text
            stream_base_url = session_url.rsplit('/', 1)[0] + '/'

        # Rewrite URLs in the playlist (keep metadata unchanged for TuneIn compatibility)
        lines = []
        for line in playlist_content.split('\n'):
            line = line.strip()

            # Keep #EXTINF metadata lines as-is (TuneIn reads these for artist/title)
            if line.startswith('#EXTINF:'):
                # Just pass through the metadata unchanged
                pass
            elif line and not line.startswith('#'):
                # This is a segment URL
                if line.startswith('http'):
                    # Absolute URL
                    segment_url = line
                else:
                    # Relative URL
                    segment_url = urljoin(stream_base_url, line)

                # Extract the full URL components to proxy
                parsed = urlparse(segment_url)
                # Encode the full original URL in the proxy path
                proxy_path = parsed.path
                if parsed.query:
                    proxy_path += '?' + parsed.query

                # Include the host and port in the proxy URL so we can reconstruct it
                proxy_url = f"{base_url}/proxy/{parsed.scheme}/{parsed.netloc}{proxy_path}"
                line = proxy_url

            lines.append(line)

        modified_playlist = '\n'.join(lines)

        logger.debug(f"Modified playlist (first 500 chars):\n{modified_playlist[:500]}")

        # Extract current track metadata for ICY headers
        current_title = None
        current_artist = None
        for line in playlist_content.split('\n'):
            if line.startswith('#EXTINF:') and 'title=' in line and 'artist=' in line:
                if 'Asset' not in line:
                    title_match = re.search(r'title="([^"]+)"', line)
                    artist_match = re.search(r'artist="([^"]+)"', line)
                    if title_match and artist_match:
                        current_title = title_match.group(1)
                        current_artist = artist_match.group(1)
                        break

        # Create response and forward cookies from origin to client
        # Add ICY headers that TuneIn might read
        headers = {
            'Cache-Control': 'no-cache',
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/vnd.apple.mpegurl'
        }

        # Add ICY metadata headers if we found track info
        if current_title and current_artist:
            headers['icy-name'] = STATION_NAME
            headers['icy-description'] = f"{current_artist} - {current_title}"
            headers['icy-genre'] = 'Pop'
            headers['icy-url'] = get_base_url()

        resp = Response(
            modified_playlist,
            headers=headers
        )

        # Forward Set-Cookie headers from origin by copying the raw header
        # This is necessary because cookies are domain-scoped and won't work through the session
        if 'Set-Cookie' in response.headers:
            set_cookie_header = response.headers['Set-Cookie']
            logger.debug(f"Forwarding Set-Cookie: {set_cookie_header}")
            # Modify the Set-Cookie header to remove domain restrictions
            # Remove Domain= attribute so cookie works on localhost
            set_cookie_header = re.sub(r';\s*Domain=[^;]+', '', set_cookie_header)
            # Remove Secure attribute for HTTP
            set_cookie_header = re.sub(r';\s*Secure', '', set_cookie_header, flags=re.IGNORECASE)
            resp.headers['Set-Cookie'] = set_cookie_header

        return resp

    except requests.RequestException as e:
        logger.error(f"Error fetching playlist: {e}")
        return Response(f"Error fetching playlist: {e}", status=502)


@app.route('/proxy/<scheme>/<path:stream_path>')
def proxy_stream(scheme, stream_path):
    """Proxy audio segments and sub-playlists"""
    # Reconstruct the original URL from the encoded path
    # stream_path contains: netloc/path?query
    original_url = f"{scheme}://{stream_path}"

    logger.info(f"Proxying: {original_url}")

    try:
        # Determine if this is a playlist or audio segment
        is_playlist = stream_path.endswith('.m3u8')

        if is_playlist:
            # Handle sub-playlists (variant playlists)
            # Forward cookies from client to origin
            cookies = dict(request.cookies)
            response = requests.get(original_url, headers=DEFAULT_HEADERS, timeout=10, cookies=cookies)
            response.raise_for_status()

            # Rewrite URLs in the sub-playlist
            stream_base_url = original_url.rsplit('/', 1)[0] + '/'
            playlist_content = response.text
            base_url = get_base_url()

            # Check if this is an infinite redirect (variant playlist with only another variant playlist)
            # If so, detect it and strip query params to get fresh stream
            lines_without_comments = [line.strip() for line in playlist_content.split('\n')
                                     if line.strip() and not line.startswith('#')]

            if (len(lines_without_comments) == 1 and
                lines_without_comments[0].endswith('.m3u8') and
                'listeningSessionID' in lines_without_comments[0]):
                # This is a redirect loop - strip the query params and request fresh
                logger.warning("Detected playlist redirect loop, requesting fresh stream")
                # Get the base playlist URL without session params
                base_playlist_url = original_url.split('?')[0]
                response = requests.get(base_playlist_url, headers=DEFAULT_HEADERS, timeout=10)
                response.raise_for_status()
                playlist_content = response.text
                logger.debug(f"Fresh playlist content: {playlist_content[:200]}")

            lines = []
            for line in playlist_content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    # This is a segment URL
                    if line.startswith('http'):
                        segment_url = line
                    else:
                        segment_url = urljoin(stream_base_url, line)

                    parsed = urlparse(segment_url)
                    proxy_path = parsed.path
                    if parsed.query:
                        proxy_path += '?' + parsed.query

                    # Include the host and port in the proxy URL
                    proxy_url = f"{base_url}/proxy/{parsed.scheme}/{parsed.netloc}{proxy_path}"
                    line = proxy_url

                lines.append(line)

            modified_content = '\n'.join(lines)

            # Create response and forward cookies from origin to client
            resp = Response(
                modified_content,
                mimetype='application/vnd.apple.mpegurl',
                headers={
                    'Cache-Control': 'no-cache',
                    'Access-Control-Allow-Origin': '*'
                }
            )

            # Forward Set-Cookie headers from origin by copying the raw header
            if 'Set-Cookie' in response.headers:
                set_cookie_header = response.headers['Set-Cookie']
                logger.debug(f"Forwarding Set-Cookie: {set_cookie_header}")
                # Remove Domain= attribute so cookie works on localhost
                set_cookie_header = re.sub(r';\s*Domain=[^;]+', '', set_cookie_header)
                # Remove Secure attribute for HTTP
                set_cookie_header = re.sub(r';\s*Secure', '', set_cookie_header, flags=re.IGNORECASE)
                resp.headers['Set-Cookie'] = set_cookie_header

            return resp
        else:
            # Stream audio segments
            # Forward cookies from client to origin
            cookies = dict(request.cookies)
            response = requests.get(original_url, headers=DEFAULT_HEADERS, stream=True, timeout=10, cookies=cookies)
            response.raise_for_status()

            def generate():
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk

            # Create response and forward cookies
            resp = Response(
                stream_with_context(generate()),
                mimetype=response.headers.get('Content-Type', 'audio/aac'),
                headers={
                    'Cache-Control': response.headers.get('Cache-Control', 'no-cache'),
                    'Access-Control-Allow-Origin': '*'
                }
            )

            # Forward Set-Cookie headers from origin by copying the raw header
            if 'Set-Cookie' in response.headers:
                set_cookie_header = response.headers['Set-Cookie']
                logger.debug(f"Forwarding Set-Cookie: {set_cookie_header}")
                # Remove Domain= attribute so cookie works on localhost
                set_cookie_header = re.sub(r';\s*Domain=[^;]+', '', set_cookie_header)
                # Remove Secure attribute for HTTP
                set_cookie_header = re.sub(r';\s*Secure', '', set_cookie_header, flags=re.IGNORECASE)
                resp.headers['Set-Cookie'] = set_cookie_header

            return resp

    except requests.RequestException as e:
        logger.error(f"Error proxying stream: {e}")
        return Response(f"Error proxying stream: {e}", status=502)


@app.route('/')
def index():
    """Serve info page"""
    base_url = get_base_url()
    return f"""
    <html>
    <head><title>Fox FM Stream Proxy</title></head>
    <body>
        <h1>{STATION_NAME} - Stream Proxy</h1>
        <p>This proxy server allows you to access the Fox FM radio stream.</p>

        <h2>Stream URLs</h2>

        <h3>HLS Streams (For VLC, Web Players)</h3>
        <ul>
            <li><strong>M3U Playlist:</strong> <a href="{base_url}/stream.m3u">{base_url}/stream.m3u</a></li>
            <li><strong>HLS Playlist:</strong> <a href="{base_url}/playlist.m3u8">{base_url}/playlist.m3u8</a></li>
        </ul>

        <h3>Icecast Stream (For TuneIn, Radio Apps)</h3>
        <ul>
            <li><strong>Icecast M3U:</strong> <a href="{base_url}/stream-icecast.m3u">{base_url}/stream-icecast.m3u</a></li>
            <li><strong>Direct Stream:</strong> <a href="{base_url}/icecast">{base_url}/icecast</a></li>
        </ul>
        <p><em>Use the Icecast URLs above for apps like TuneIn that require metadata support.</em></p>

        <h2>Usage</h2>
        <p><strong>For VLC/iTunes:</strong> Use the HLS M3U playlist URL<br>
        <strong>For TuneIn/Radio Apps:</strong> Use the Icecast M3U playlist URL</p>

        <h2>Status</h2>
        <p>Server is running on port {PORT}</p>
    </body>
    </html>
    """


@app.route('/health')
def health():
    """Health check endpoint"""
    return {'status': 'ok', 'station': STATION_NAME}


@app.route('/nowplaying')
def now_playing():
    """Get current playing track information from the playlist"""
    try:
        # Get a valid session URL
        session_url = get_valid_session_url(STREAM_URL)

        # Fetch the media playlist
        response = requests.get(session_url, headers=DEFAULT_HEADERS, timeout=10)
        response.raise_for_status()

        # Parse the playlist to extract now playing info
        playlist_content = response.text

        # Look for #EXTINF lines with metadata
        for line in playlist_content.split('\n'):
            if line.startswith('#EXTINF:') and 'title=' in line and 'artist=' in line:
                # Parse the metadata
                # Format: #EXTINF:duration,title="Song",artist="Artist",url="https://..."
                title_match = re.search(r'title="([^"]+)"', line)
                artist_match = re.search(r'artist="([^"]+)"', line)
                url_match = re.search(r'url="([^"]+)"', line)

                if title_match and artist_match:
                    title = title_match.group(1)
                    artist = artist_match.group(1)

                    # Filter out "Asset" metadata (commercials/station IDs)
                    if 'Asset' in title or 'Asset' in artist:
                        logger.debug(f"Skipping Asset metadata: {title} - {artist}")
                        continue

                    return {
                        'status': 'ok',
                        'station': STATION_NAME,
                        'title': title,
                        'artist': artist,
                        'artwork': url_match.group(1) if url_match else None,
                        'album': STATION_NAME
                    }

        # No metadata found
        return {
            'status': 'ok',
            'station': STATION_NAME,
            'title': 'Live Stream',
            'artist': STATION_NAME,
            'artwork': None,
            'album': STATION_NAME
        }

    except Exception as e:
        logger.error(f"Error fetching now playing: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'station': STATION_NAME
        }, 500


if __name__ == '__main__':
    logger.info(f"Starting Fox FM Stream Proxy on {HOST}:{PORT}")
    logger.info(f"Stream source: {STREAM_URL}")
    logger.info(f"Access your stream at: http://localhost:{PORT}/stream.m3u")

    app.run(host=HOST, port=PORT, debug=False, threaded=True)
