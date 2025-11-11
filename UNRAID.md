# Deploying Fox FM Stream Proxy on Unraid

This guide will walk you through deploying the Fox FM Stream Proxy as a Docker container on your Unraid server.

## Prerequisites

- Unraid 6.9+ with Docker support enabled
- Community Applications (CA) plugin installed (optional, for easier management)
- Basic familiarity with Unraid's Docker interface

## Deployment Methods

### Method 1: Using Docker Compose (Recommended)

This method uses Unraid's built-in docker-compose support (available in Unraid 6.11+).

#### Step 1: Enable Docker Compose

1. Go to **Settings** → **Docker**
2. Enable **Docker Compose Support** if not already enabled
3. Click **Apply**

#### Step 2: Create Compose File

1. SSH into your Unraid server or use the terminal
2. Create a directory for the project:
   ```bash
   mkdir -p /mnt/user/appdata/fox-fm-proxy
   cd /mnt/user/appdata/fox-fm-proxy
   ```

3. Clone the repository or create the files manually:
   ```bash
   git clone https://github.com/YOUR_USERNAME/fox-fm.git .
   ```

   Or download the files manually via the Unraid web interface.

#### Step 3: Deploy the Stack

1. Navigate to **Docker** tab in Unraid
2. Click **Compose** button at the bottom
3. Click **Add New Stack**
4. Name it: `fox-fm-proxy`
5. Set the compose file path: `/mnt/user/appdata/fox-fm-proxy/docker-compose.yml`
6. Click **Compose Up**

The container will now start automatically and will restart on boot.

---

### Method 2: Manual Docker Container Setup

If you prefer to set up the container manually through Unraid's Docker interface:

#### Step 1: Prepare the Application Files

1. SSH into your Unraid server or use the terminal
2. Create the application directory:
   ```bash
   mkdir -p /mnt/user/appdata/fox-fm-proxy
   cd /mnt/user/appdata/fox-fm-proxy
   ```

3. Copy the following files to this directory:
   - `stream_proxy.py`
   - `requirements.txt`
   - `Dockerfile`

   You can either:
   - Clone via git: `git clone https://github.com/YOUR_USERNAME/fox-fm.git /mnt/user/appdata/fox-fm-proxy`
   - Or upload files via SMB/NFS share

#### Step 2: Build the Docker Image

1. SSH into your Unraid server
2. Build the image:
   ```bash
   cd /mnt/user/appdata/fox-fm-proxy
   docker build -t fox-fm-proxy:latest .
   ```

#### Step 3: Add Container via Unraid Web UI

1. Go to the **Docker** tab in Unraid
2. Click **Add Container** at the bottom
3. Fill in the following settings:

   **Basic Settings:**
   - **Name:** `fox-fm-proxy`
   - **Repository:** `fox-fm-proxy:latest`
   - **Docker Hub URL:** (leave blank - using local image)
   - **Icon URL:** `https://raw.githubusercontent.com/YOUR_USERNAME/fox-fm/main/icon.png` (optional)

   **Network Type:**
   - **Network Type:** `bridge`
   - **Port Mappings:**
     - **Container Port:** `8000`
     - **Host Port:** `8000`
     - **Connection Type:** `TCP`

   **Environment Variables:**
   Click **Add another Path, Port, Variable, Label or Device** for each:
   - **Key:** `PORT` **Value:** `8000`
   - **Key:** `HOST` **Value:** `0.0.0.0`
   - **Key:** `LOG_LEVEL` **Value:** `INFO`
   - **Key:** `STREAM_URL` **Value:** `https://sa46.scastream.com.au/live/3fox_128.stream/playlist.m3u8`
   - **Key:** `STATION_NAME` **Value:** `101.9 Fox FM Melbourne`

   **Docker Settings:**
   - **Privileged:** `Off`
   - **Console shell command:** `Bash`

   **Restart Policy:**
   - **Autostart:** `Yes` ✓
   - **Restart Policy:** `unless-stopped`

4. Click **Apply**

The container will now start and will automatically start on server boot.

---

## Verification

### Check Container Status

1. Go to **Docker** tab in Unraid
2. Verify the `fox-fm-proxy` container shows as **Started** (green play icon)
3. Check the container logs by clicking the container icon → **Logs**

### Test the Stream

1. Open a web browser and navigate to: `http://YOUR-UNRAID-IP:8000`
2. You should see the Fox FM Stream Proxy info page
3. Test the stream in VLC:
   - Open VLC
   - Go to **Media** → **Open Network Stream**
   - Enter: `http://YOUR-UNRAID-IP:8000/stream.m3u`
   - Click **Play**

### Health Check

Check the health endpoint:
```bash
curl http://YOUR-UNRAID-IP:8000/health
```

You should see: `{"status":"ok","station":"101.9 Fox FM Melbourne"}`

---

## Configuration

### Changing the Port

If port 8000 is already in use on your Unraid server:

**Docker Compose Method:**
1. Edit `docker-compose.yml`
2. Change the port mapping: `"8080:8000"` (where 8080 is the new host port)
3. Re-deploy: **Compose** → **Compose Down** → **Compose Up**

**Manual Method:**
1. Click the container icon → **Edit**
2. Change **Host Port** to your desired port (e.g., `8080`)
3. Click **Apply**

### Environment Variables

You can customize the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Internal container port (don't change unless you know what you're doing) |
| `HOST` | `0.0.0.0` | Bind address (leave as default) |
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `STREAM_URL` | See compose file | The source HLS stream URL |
| `STATION_NAME` | `101.9 Fox FM Melbourne` | Display name for the station |

---

## Automatic Updates

### Method 1: Using Watchtower (Recommended)

Install the Watchtower container from Community Applications to automatically update your containers:

1. Go to **Apps** tab
2. Search for **Watchtower**
3. Install and configure to monitor your containers
4. Watchtower will automatically pull and deploy updates

### Method 2: Manual Updates

**Docker Compose:**
```bash
cd /mnt/user/appdata/fox-fm-proxy
git pull
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

**Manual Container:**
```bash
cd /mnt/user/appdata/fox-fm-proxy
git pull
docker build -t fox-fm-proxy:latest --no-cache .
docker stop fox-fm-proxy
docker rm fox-fm-proxy
# Then recreate via Unraid UI or docker run command
```

---

## Accessing the Stream on Your Network

Once deployed, access the stream from any device on your network:

- **M3U Playlist:** `http://YOUR-UNRAID-IP:8000/stream.m3u`
- **HLS Playlist:** `http://YOUR-UNRAID-IP:8000/playlist.m3u8`
- **Web Player:** `http://YOUR-UNRAID-IP:8000/player.html`
- **Now Playing API:** `http://YOUR-UNRAID-IP:8000/nowplaying`

### External Access (Optional)

To access the stream outside your home network:

1. Set up a reverse proxy (recommended: Nginx Proxy Manager, available in CA)
2. Configure SSL/TLS certificate
3. Set up port forwarding on your router (not recommended for security)
4. Use a VPN to access your home network (most secure option)

---

## Troubleshooting

### Container Won't Start

1. Check logs: Click container icon → **Logs**
2. Verify all files are in `/mnt/user/appdata/fox-fm-proxy`
3. Ensure port 8000 is not already in use: `netstat -tulpn | grep 8000`
4. Rebuild the image with `--no-cache` flag

### Stream Not Playing

1. Check container is running: **Docker** tab → verify green play icon
2. Test health endpoint: `curl http://YOUR-UNRAID-IP:8000/health`
3. Check logs for errors
4. Verify source stream is accessible: `curl -I https://sa46.scastream.com.au/live/3fox_128.stream/playlist.m3u8`
5. Try increasing `LOG_LEVEL` to `DEBUG` and check logs

### Port Conflicts

If you get "port already in use" error:
```bash
# Find what's using port 8000
netstat -tulpn | grep 8000
# Or use lsof
lsof -i :8000
```

Change to a different port in your configuration.

### Container Not Auto-Starting on Boot

1. Verify **Autostart** is enabled in container settings
2. Check Docker service is set to auto-start: **Settings** → **Docker** → **Enable Docker:** `Yes`
3. Verify restart policy is set to `unless-stopped`

---

## Monitoring and Logs

### View Live Logs

**Via Unraid UI:**
1. **Docker** tab → Click container icon → **Logs**

**Via SSH:**
```bash
docker logs -f fox-fm-proxy
```

### Log Rotation

Unraid automatically manages Docker logs. To customize:

1. **Settings** → **Docker**
2. Adjust **Docker log rotation** settings

---

## Backup

To backup your configuration:

```bash
# Backup the entire directory
tar -czf fox-fm-proxy-backup.tar.gz /mnt/user/appdata/fox-fm-proxy

# Restore
tar -xzf fox-fm-proxy-backup.tar.gz -C /
```

Include this directory in your Unraid backup strategy (e.g., CA Backup/Restore Appdata plugin).

---

## Resource Usage

Expected resource usage:
- **RAM:** ~100-200 MB (with 4 Gunicorn workers)
- **CPU:** <5% during normal operation
- **Disk:** ~50 MB (application + dependencies)
- **Network:** Depends on number of concurrent listeners

---

## Security Considerations

1. **Internal Use Only:** This proxy is designed for personal/home use
2. **No Authentication:** The proxy has no built-in authentication
3. **Reverse Proxy:** If exposing externally, use a reverse proxy with authentication
4. **Firewall:** Don't expose port 8000 directly to the internet
5. **VPN Access:** Use VPN for secure remote access instead of port forwarding

---

## Support

For issues or questions:
- Check the main [README.md](README.md)
- Review container logs for errors
- Open an issue on GitHub
- Check Unraid forums for Docker-specific issues

---

## License

MIT License - See [LICENSE](LICENSE) file for details
