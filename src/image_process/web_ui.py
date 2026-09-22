import os
import json
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
import webbrowser

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cheki Crop - Web Review</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #111827; color: white; user-select: none; }
        .thumbnail { cursor: pointer; transition: 0.2s; border: 2px solid transparent; }
        .thumbnail:hover { border-color: #9ca3af; }
        .thumbnail.active { border-color: #3b82f6; background-color: #1f2937; }
        canvas { cursor: crosshair; }
        
        /* Custom scrollbar */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #1f2937; }
        ::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #6b7280; }
    </style>
</head>
<body class="flex h-screen overflow-hidden text-sm">
    <!-- Sidebar -->
    <div class="w-72 bg-gray-900 border-r border-gray-700 flex flex-col shadow-xl z-10">
        <div class="p-4 bg-gray-800 font-bold text-lg text-center shadow-md border-b border-gray-700 flex justify-between items-center">
            <span>Cheki Crop</span>
            <span id="counter" class="text-xs bg-gray-700 px-2 py-1 rounded text-gray-300">0/0</span>
        </div>
        <div id="gallery" class="flex-1 overflow-y-auto p-3 grid grid-cols-2 gap-2 content-start">
            <!-- Thumbnails go here -->
        </div>
        <div class="p-4 bg-gray-800 border-t border-gray-700">
            <button id="btn-submit" class="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 px-4 rounded shadow-lg transition-colors">
                Save & Crop All
            </button>
        </div>
    </div>
    
    <!-- Main Area -->
    <div class="flex-1 flex flex-col relative bg-gray-800">
        <div class="p-4 bg-gray-900 shadow-md border-b border-gray-700 flex justify-between items-center" id="header">
            <div class="font-mono text-gray-300 flex items-center gap-3">
                <span id="filename">Select an image</span>
                <span id="status-badge" class="hidden text-xs px-2 py-0.5 rounded bg-blue-900 text-blue-200">Edited</span>
            </div>
            <div class="text-gray-400 text-xs">
                Drag the green corners to adjust crop area
            </div>
        </div>
        
        <div class="flex-1 flex justify-center items-center overflow-hidden p-6 relative" id="canvas-container">
            <div class="absolute inset-0 flex items-center justify-center pointer-events-none" id="loading-overlay">
                <div class="animate-pulse text-gray-500">Loading Image...</div>
            </div>
            <canvas id="canvas" class="shadow-2xl rounded opacity-0 transition-opacity duration-300"></canvas>
        </div>
        
        <!-- Keyboard shortcuts hint -->
        <div class="absolute bottom-4 right-4 text-xs text-gray-500 bg-gray-900 bg-opacity-70 px-3 py-2 rounded pointer-events-none">
            Up/Down: Navigate images
        </div>
    </div>

    <script>
        let items = [];
        let currentIndex = -1;
        let imgObj = null;
        let scale = 1.0;
        let draggingIdx = -1;
        
        const canvas = document.getElementById('canvas');
        const ctx = canvas.getContext('2d');
        const gallery = document.getElementById('gallery');
        const overlay = document.getElementById('loading-overlay');
        
        async function loadData() {
            const res = await fetch('/api/data');
            items = await res.json();
            
            // Add edited flag
            items.forEach(item => item.edited = false);
            
            document.getElementById('counter').innerText = `${items.length} images`;
            renderGallery();
            if(items.length > 0) {
                selectItem(0);
            }
        }
        
        function renderGallery() {
            gallery.innerHTML = '';
            items.forEach((item, idx) => {
                const div = document.createElement('div');
                div.className = 'thumbnail p-1 rounded bg-gray-800 relative shadow-sm group';
                div.innerHTML = `
                    <div class="relative overflow-hidden rounded">
                        <img src="/image?path=${encodeURIComponent(item.path)}" class="w-full h-24 object-cover transform group-hover:scale-105 transition-transform duration-500 pointer-events-none">
                        <div class="absolute inset-0 bg-black opacity-0 group-hover:opacity-10 transition-opacity"></div>
                    </div>
                    <div class="text-xs text-center mt-1 truncate text-gray-400 font-mono" title="${item.filename}">${item.filename}</div>
                    <div id="badge-${idx}" class="absolute top-1 right-1 w-2 h-2 rounded-full bg-blue-500 hidden shadow"></div>
                `;
                div.onclick = () => selectItem(idx);
                gallery.appendChild(div);
            });
            updateGallerySelection();
        }
        
        function updateGallerySelection() {
            const children = gallery.children;
            for(let i=0; i<children.length; i++) {
                if(i === currentIndex) {
                    children[i].classList.add('active');
                    children[i].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                } else {
                    children[i].classList.remove('active');
                }
                
                // Show badge if edited
                const badge = document.getElementById(`badge-${i}`);
                if(badge) badge.style.display = items[i].edited ? 'block' : 'none';
            }
        }
        
        function selectItem(idx) {
            if(idx < 0 || idx >= items.length) return;
            currentIndex = idx;
            updateGallerySelection();
            
            document.getElementById('filename').innerHTML = `<b class="text-white">${items[idx].filename}</b>`;
            const badge = document.getElementById('status-badge');
            badge.style.display = items[idx].edited ? 'block' : 'none';
            
            canvas.style.opacity = '0';
            overlay.style.display = 'flex';
            
            imgObj = new Image();
            imgObj.src = `/image?path=${encodeURIComponent(items[idx].path)}`;
            imgObj.onload = () => {
                overlay.style.display = 'none';
                canvas.style.opacity = '1';
                resizeCanvas();
                draw();
            };
        }
        
        function resizeCanvas() {
            if(!imgObj) return;
            const container = document.getElementById('canvas-container');
            const cw = container.clientWidth - 40; // padding
            const ch = container.clientHeight - 40;
            const iw = imgObj.width;
            const ih = imgObj.height;
            
            scale = Math.min(cw / iw, ch / ih);
            canvas.width = iw * scale;
            canvas.height = ih * scale;
        }
        
        function draw() {
            if(!imgObj || currentIndex === -1) return;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.drawImage(imgObj, 0, 0, canvas.width, canvas.height);
            
            const pts = items[currentIndex].points;
            
            // Draw dimming overlay outside crop
            ctx.fillStyle = 'rgba(0,0,0,0.5)';
            ctx.beginPath();
            ctx.rect(0, 0, canvas.width, canvas.height);
            ctx.moveTo(pts[0][0]*scale, pts[0][1]*scale);
            for(let i=1; i<4; i++) ctx.lineTo(pts[i][0]*scale, pts[i][1]*scale);
            ctx.closePath();
            ctx.fill('evenodd');
            
            // Draw polygon outline
            ctx.beginPath();
            ctx.moveTo(pts[0][0]*scale, pts[0][1]*scale);
            for(let i=1; i<4; i++) {
                ctx.lineTo(pts[i][0]*scale, pts[i][1]*scale);
            }
            ctx.closePath();
            ctx.lineWidth = 2;
            ctx.strokeStyle = '#22c55e'; // green-500
            ctx.stroke();
            
            // Draw corners
            for(let i=0; i<4; i++) {
                ctx.beginPath();
                ctx.arc(pts[i][0]*scale, pts[i][1]*scale, 6, 0, Math.PI*2);
                ctx.fillStyle = (i === draggingIdx) ? '#ef4444' : '#22c55e';
                ctx.fill();
                ctx.lineWidth = 1.5;
                ctx.strokeStyle = 'white';
                ctx.stroke();
                
                // Inner dot for precision
                ctx.beginPath();
                ctx.arc(pts[i][0]*scale, pts[i][1]*scale, 1, 0, Math.PI*2);
                ctx.fillStyle = 'white';
                ctx.fill();
            }
            
            // Draw Magnifying Glass (Loupe) when dragging
            if(draggingIdx !== -1) {
                const px = pts[draggingIdx][0]*scale;
                const py = pts[draggingIdx][1]*scale;
                
                const loupeRadius = 60;
                const loupeZoom = 3.0; // 3x zoom
                
                // Position loupe away from cursor
                let lx = px + 90;
                let ly = py - 90;
                
                // Keep loupe within canvas bounds
                if(lx + loupeRadius > canvas.width) lx = px - 90;
                if(ly - loupeRadius < 0) ly = py + 90;

                ctx.save();
                ctx.beginPath();
                ctx.arc(lx, ly, loupeRadius, 0, Math.PI*2);
                ctx.clip();
                
                // Draw zoomed image
                // Calculate source rect
                const sx = pts[draggingIdx][0] - (loupeRadius / loupeZoom / scale);
                const sy = pts[draggingIdx][1] - (loupeRadius / loupeZoom / scale);
                const sw = (loupeRadius * 2) / loupeZoom / scale;
                const sh = (loupeRadius * 2) / loupeZoom / scale;
                
                ctx.drawImage(imgObj, sx, sy, sw, sh, lx - loupeRadius, ly - loupeRadius, loupeRadius * 2, loupeRadius * 2);
                
                // Draw crosshair
                ctx.beginPath();
                ctx.moveTo(lx - 15, ly);
                ctx.lineTo(lx + 15, ly);
                ctx.moveTo(lx, ly - 15);
                ctx.lineTo(lx, ly + 15);
                ctx.strokeStyle = '#ef4444'; // red
                ctx.lineWidth = 1.5;
                ctx.stroke();
                
                ctx.restore();
                
                // Draw loupe border
                ctx.beginPath();
                ctx.arc(lx, ly, loupeRadius, 0, Math.PI*2);
                ctx.strokeStyle = 'white';
                ctx.lineWidth = 4;
                ctx.stroke();
                ctx.strokeStyle = '#3b82f6'; // blue outer border
                ctx.lineWidth = 1;
                ctx.stroke();
            }
        }
        
        function getMousePos(e) {
            const rect = canvas.getBoundingClientRect();
            // Calculate scale in case canvas display size differs from coordinate size
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            return {
                x: (e.clientX - rect.left) * scaleX,
                y: (e.clientY - rect.top) * scaleY
            };
        }
        
        canvas.addEventListener('mousedown', (e) => {
            if(currentIndex === -1) return;
            const pos = getMousePos(e);
            const pts = items[currentIndex].points;
            
            let minDist = 40; // grab radius
            draggingIdx = -1;
            for(let i=0; i<4; i++) {
                const px = pts[i][0]*scale;
                const py = pts[i][1]*scale;
                const dist = Math.hypot(pos.x - px, pos.y - py);
                if(dist < minDist) {
                    minDist = dist;
                    draggingIdx = i;
                }
            }
            if(draggingIdx !== -1) draw();
        });
        
        canvas.addEventListener('mousemove', (e) => {
            if(draggingIdx !== -1) {
                const pos = getMousePos(e);
                // Constrain within image
                let nx = Math.max(0, Math.min(pos.x / scale, imgObj.width));
                let ny = Math.max(0, Math.min(pos.y / scale, imgObj.height));
                items[currentIndex].points[draggingIdx] = [nx, ny];
                if (!items[currentIndex].edited) {
                    items[currentIndex].edited = true;
                    if (!items[currentIndex].method.includes("+WebUI")) {
                        items[currentIndex].method += "+WebUI";
                    }
                }
                
                // Update badge live
                document.getElementById('status-badge').style.display = 'block';
                const badge = document.getElementById(`badge-${currentIndex}`);
                if(badge) badge.style.display = 'block';
                
                draw();
            }
        });
        
        window.addEventListener('mouseup', () => {
            if(draggingIdx !== -1) {
                draggingIdx = -1;
                draw();
            }
        });
        
        window.addEventListener('resize', () => {
            resizeCanvas();
            draw();
        });
        
        // Keyboard navigation
        window.addEventListener('keydown', (e) => {
            if(e.key === 'ArrowDown' || e.key === 'ArrowRight') {
                selectItem(currentIndex + 1);
            } else if(e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
                selectItem(currentIndex - 1);
            }
        });
        
        document.getElementById('btn-submit').addEventListener('click', async () => {
            const btn = document.getElementById('btn-submit');
            btn.innerText = "Processing, please wait...";
            btn.disabled = true;
            btn.classList.add('opacity-50', 'cursor-not-allowed');
            
            await fetch('/api/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(items)
            });
            
            document.body.innerHTML = `
                <div class='flex flex-col w-full h-full items-center justify-center bg-gray-900'>
                    <svg class="w-20 h-20 text-green-500 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    <div class="text-3xl text-white font-bold">Processed Successfully!</div>
                    <div class="text-gray-400 mt-2">You can close this window and return to the terminal.</div>
                </div>
            `;
        });
        
        loadData();
    </script>
</body>
</html>
"""

class ReviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server, review_data, result_callback):
        self.review_data = review_data
        self.result_callback = result_callback
        super().__init__(request, client_address, server)
        
    def log_message(self, format, *args):
        pass # Suppress logs
        
    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        url = urlparse(self.path)
        
        if url.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
            
        elif url.path == '/api/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json; charset=utf-8')
            self.end_headers()
            self.wfile.write(json.dumps(self.review_data).encode('utf-8'))
            
        elif url.path == '/image':
            query = parse_qs(url.query)
            if 'path' in query:
                filepath = query['path'][0]
                if os.path.exists(filepath):
                    self.send_response(200)
                    self.send_header('Content-type', 'image/jpeg')
                    self.end_headers()
                    with open(filepath, 'rb') as f:
                        self.wfile.write(f.read())
                    return
            self.send_response(404)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/api/save':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            results = json.loads(post_data.decode('utf-8'))
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
            
            # Send results back to main thread and shutdown
            self.result_callback(results)
            threading.Thread(target=self.server.shutdown).start()

def start_web_review(items_data):
    """
    Starts local server.
    items_data: list of dicts: {"filename": "...", "path": "...", "points": [[x,y],...], "method": "..."}
    Returns updated items_data
    """
    final_results = []
    
    def on_result(results):
        nonlocal final_results
        final_results = results
        
    def handler_factory(*args, **kwargs):
        return ReviewHandler(*args, review_data=items_data, result_callback=on_result, **kwargs)
        
    server = None
    port = 8085
    for p in range(8085, 8095):
        try:
            HTTPServer.allow_reuse_address = True
            server = HTTPServer(('127.0.0.1', p), handler_factory)
            port = p
            break
        except OSError:
            continue
            
    if server is None:
        print("[錯誤] 無法啟動 Web UI，所有連接埠皆被佔用。")
        return items_data

    print("\n" + "="*60)
    print(" [Web UI 審查模式啟動]")
    print(f" 伺服器運行於: http://127.0.0.1:{port}")
    print(" 正在為您自動打開瀏覽器...")
    print(" 請在網頁上完成所有調整後，按下左下角的「Save & Crop All」按鈕！")
    print("="*60 + "\n")
    
    webbrowser.open(f"http://127.0.0.1:{port}")
    
    # Blocks until shutdown is called
    server.serve_forever()
    server.server_close()
    
    return final_results
