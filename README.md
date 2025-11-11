# Fox FM Stream Proxy

A Python-based HLS stream proxy for 101.9 Fox FM Melbourne. This application captures the radio station's live stream and re-serves it through a local server, allowing you to use the stream in any media player that supports M3U/HLS playlists.

## Features

- Proxies the Fox FM HLS audio stream
- Provides a simple M3U playlist URL
- Maintains session state with the source stream
- Handles both master playlists and audio segments
- CORS-enabled for web players
- Docker support for easy deployment

## Requirements

- Python 3.11+
- Flask
- requests
- Flask-CORS

## Quick Start (Local Development)

### 1. Clone and Setup

```bash
cd fox-fm
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run the Server

```bash
python stream_proxy.py
```

The server will start on `http://localhost:8000`

### 3. Use the Stream

Open your media player (VLC, iTunes, etc.) and load:

```
http://localhost:8000/stream.m3u
```

Or access the HLS playlist directly:

```
http://localhost:8000/playlist.m3u8
```

## Configuration

You can customize the server using environment variables. Copy `.env.example` to `.env` and modify:

```bash
PORT=8000                    # Server port
HOST=0.0.0.0                # Bind address (0.0.0.0 for all interfaces)
LOG_LEVEL=INFO              # Logging level (DEBUG, INFO, WARNING, ERROR)
```

## Testing with VLC

1. Open VLC Media Player
2. Go to **Media** → **Open Network Stream**
3. Enter: `http://localhost:8000/stream.m3u`
4. Click **Play**

## Docker Deployment (Recommended for 24/7)

The Docker setup uses Gunicorn for production-grade performance with:
- 4 worker processes for handling concurrent requests
- Automatic health checks
- Auto-restart on failure
- Production-optimized configuration

### Build and Run with Docker Compose

```bash
# Build and start the container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the container
docker-compose down
```

The stream will be available at `http://localhost:8000/stream.m3u`

### Build Docker Image Manually

```bash
docker build -t fox-fm-proxy .
docker run -d -p 8000:8000 --name fox-fm-proxy --restart unless-stopped fox-fm-proxy
```

### Environment Variables

You can customize the proxy using environment variables in `docker-compose.yml`:

```yaml
environment:
  - PORT=8000                    # Server port
  - HOST=0.0.0.0                # Bind address
  - LOG_LEVEL=INFO              # Logging level (DEBUG, INFO, WARNING, ERROR)
  - STREAM_URL=https://...      # Source stream URL
  - STATION_NAME=101.9 Fox FM Melbourne  # Station name
```

## Endpoints

### HLS Endpoints (For VLC, Web Players)
- `/` - Info page with available URLs
- `/stream.m3u` - M3U playlist file (HLS)
- `/playlist.m3u8` - HLS master playlist
- `/proxy/<path>` - Proxied audio segments

### Icecast Endpoints (For TuneIn, Radio Apps)
- `/stream-icecast.m3u` - M3U playlist file (Icecast stream)
- `/icecast` - Direct Icecast-compatible stream with ICY metadata
- `/nowplaying` - JSON API for current track metadata

### Other Endpoints
- `/health` - Health check endpoint

## Stream Format Compatibility

**Use HLS endpoints for:**
- VLC Media Player
- Web browsers with HLS.js
- iTunes/Apple Music
- Most desktop media players

**Use Icecast endpoint for:**
- TuneIn Radio app
- Radio apps that require ICY metadata
- Apps that don't support HLS
- Players that need artist/title/artwork metadata

The Icecast endpoint converts the HLS stream to a continuous stream with embedded ICY metadata, which is what most radio apps expect.

## How It Works

1. The proxy server fetches the HLS master playlist from the Fox FM stream
2. It rewrites all segment URLs to point to the local proxy server
3. When a media player requests segments, they are fetched from the source and streamed through the proxy
4. Session cookies and headers are maintained to keep the connection alive

## Troubleshooting

### Stream not playing

- Check that the server is running: `curl http://localhost:8000/health`
- Verify the source stream is accessible: Check network logs
- Try increasing LOG_LEVEL to DEBUG for more information

### Port already in use

Change the PORT environment variable:

```bash
PORT=8080 python stream_proxy.py
```

## License

MIT

## Disclaimer

This tool is for personal use only. Ensure you comply with the radio station's terms of service and copyright laws in your jurisdiction.