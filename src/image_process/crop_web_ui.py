import os
import json
import threading
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>照片裁切設定 (套用至所有照片)</title>
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Cropper.js CSS -->
    <link href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.css" rel="stylesheet">
    <style>
        body { background-color: #111827; color: white; user-select: none; margin: 0; overflow: hidden; }
        #canvas-container { height: calc(100vh - 140px); width: 100%; display: flex; justify-content: center; align-items: center; background-color: #1f2937; }
        img { display: block; max-width: 100%; }
        /* Cropper customization for Apple Photos style */
        .cropper-view-box { outline: 2px solid #3b82f6; outline-color: rgba(59, 130, 246, 0.75); }
        .cropper-line, .cropper-point { background-color: #3b82f6; }
        .cropper-point.point-se { width: 10px; height: 10px; }
    </style>
</head>
<body class="flex flex-col h-screen text-sm">
    <!-- Header/Toolbar -->
    <div class="h-16 bg-gray-900 border-b border-gray-700 flex justify-between items-center px-6 shadow-md z-10">
        <div class="font-bold text-lg text-gray-200">
            裁切設定 <span class="text-xs font-normal text-gray-400 ml-2">(此裁切設定將會套用至所有選取的照片)</span>
        </div>
        
        <div class="flex space-x-2">
            <button class="aspect-btn bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded transition" data-ratio="NaN">自由裁切</button>
            <button class="aspect-btn bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded transition" data-ratio="1">1:1 (方形)</button>
            <button class="aspect-btn bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded transition" data-ratio="1.33333333333">4:3 (橫)</button>
            <button class="aspect-btn bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded transition" data-ratio="0.75">3:4 (直)</button>
            <button class="aspect-btn bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded transition" data-ratio="1.77777777778">16:9 (橫)</button>
            <button class="aspect-btn bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded transition" id="btn-orig-landscape">原圖比例 (橫)</button>
            <button class="aspect-btn bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded transition" id="btn-orig-portrait">原圖比例 (直)</button>
        </div>
    </div>

    <!-- Main Workspace -->
    <div id="canvas-container">
        <img id="image" src="/image" alt="Picture">
    </div>

    <!-- Footer -->
    <div class="h-auto py-3 bg-gray-900 border-t border-gray-700 flex justify-between items-center px-6 shadow-md z-10">
        <div class="text-gray-400 text-xs space-y-1">
            <div><span class="text-blue-400 font-bold">目前狀態:</span> <span id="status-ratio">自由裁切</span></div>
            <div>💡 <span class="text-gray-300">觸控板兩指：</span>縮放照片 | <span class="text-gray-300">拖曳：</span>移動照片 | <span class="text-gray-300">雙擊照片：</span>100% / 適應畫面</div>
        </div>
        <div class="flex space-x-4">
            <button id="btn-reset" class="bg-gray-700 hover:bg-gray-600 text-white font-bold py-2 px-6 rounded transition">
                重設
            </button>
            <button id="btn-submit" class="bg-blue-600 hover:bg-blue-500 text-white font-bold py-2 px-8 rounded shadow-lg transition transform hover:scale-105">
                儲存並套用至所有照片
            </button>
        </div>
    </div>

    <!-- Cropper.js -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.5.13/cropper.min.js"></script>
    <script>
        const image = document.getElementById('image');
        let cropper;
        let originalRatio = NaN;

        image.onload = function() {
            if(cropper) cropper.destroy();
            
            const rawRatio = image.naturalWidth / image.naturalHeight;
            let landscapeRatio = rawRatio >= 1 ? rawRatio : 1 / rawRatio;
            let portraitRatio = rawRatio < 1 ? rawRatio : 1 / rawRatio;
            
            document.getElementById('btn-orig-landscape').dataset.ratio = landscapeRatio;
            document.getElementById('btn-orig-portrait').dataset.ratio = portraitRatio;
            
            cropper = new Cropper(image, {
                viewMode: 1, // Restrict the crop box not to exceed the size of the canvas
                dragMode: 'move', // default to moving image (like Apple Photos)
                aspectRatio: NaN,
                autoCropArea: 0.9,
                restore: false,
                guides: true,
                center: true,
                highlight: false,
                cropBoxMovable: true,
                cropBoxResizable: true,
                toggleDragModeOnDblclick: false, // We'll handle dblclick manually for zoom
                zoomOnWheel: false, // Disable default zoom on wheel to implement custom pan/zoom
            });
        };

        // Aspect ratio buttons
        document.querySelectorAll('.aspect-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                // Update active state
                document.querySelectorAll('.aspect-btn').forEach(b => {
                    b.classList.remove('bg-blue-600', 'text-white');
                    b.classList.add('bg-gray-800', 'text-gray-300');
                });
                e.target.classList.remove('bg-gray-800', 'text-gray-300');
                e.target.classList.add('bg-blue-600', 'text-white');

                const ratio = parseFloat(e.target.dataset.ratio);
                cropper.setAspectRatio(ratio);
                
                document.getElementById('status-ratio').innerText = isNaN(ratio) ? '自由裁切' : e.target.innerText;
            });
        });

        // Highlight "自由裁切" initially
        document.querySelector('.aspect-btn[data-ratio="NaN"]').classList.add('bg-blue-600', 'text-white');

        // Reset
        document.getElementById('btn-reset').addEventListener('click', () => {
            cropper.reset();
            document.querySelector('.aspect-btn[data-ratio="NaN"]').click();
        });

        // Custom double click to toggle 100% / fit zoom
        let isZoomedIn = false;
        document.getElementById('canvas-container').addEventListener('dblclick', () => {
            if (isZoomedIn) {
                const containerData = cropper.getContainerData();
                const imageRatio = image.naturalWidth / image.naturalHeight;
                const containerRatio = containerData.width / containerData.height;
                
                let fitScale = 1;
                if (imageRatio > containerRatio) {
                    fitScale = containerData.width / image.naturalWidth;
                } else {
                    fitScale = containerData.height / image.naturalHeight;
                }
                
                cropper.zoomTo(fitScale);
                isZoomedIn = false;
            } else {
                cropper.zoomTo(1);
                isZoomedIn = true;
            }
        });

        // Trackpad panning & zooming
        document.getElementById('canvas-container').addEventListener('wheel', (e) => {
            e.preventDefault();
            if (e.ctrlKey) {
                // Pinch to zoom (trackpad pinch gesture usually triggers wheel with ctrlKey)
                const ratio = 1 - (e.deltaY * 0.01);
                // cropper.zoom(ratio) is relative ratio increment, but cropper.zoom() takes a ratio delta.
                // It's easier to use cropper.zoom() with a small positive or negative value.
                cropper.zoom(-e.deltaY * 0.01);
            } else {
                // Two-finger scroll to pan
                cropper.move(-e.deltaX, -e.deltaY);
            }
        }, { passive: false });

        // Submit
        document.getElementById('btn-submit').addEventListener('click', async () => {
            const btn = document.getElementById('btn-submit');
            btn.innerText = "處理中...";
            btn.disabled = true;
            btn.classList.add('opacity-50', 'cursor-not-allowed');

            const data = cropper.getData(true); // rounded values
            // data contains: x, y, width, height, rotate, scaleX, scaleY

            await fetch('/api/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    x: data.x,
                    y: data.y,
                    width: data.width,
                    height: data.height
                })
            });

            document.body.innerHTML = `
                <div class='flex flex-col w-full h-full items-center justify-center bg-gray-900'>
                    <svg class="w-20 h-20 text-green-500 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                    <div class="text-3xl text-white font-bold">裁切設定已儲存！</div>
                    <div class="text-gray-400 mt-2">您可以關閉此網頁並回到終端機繼續處理。</div>
                </div>
            `;
        });
    </script>
</body>
</html>
"""

class CropReviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, request, client_address, server, image_path, result_callback):
        self.image_path = image_path
        self.result_callback = result_callback
        super().__init__(request, client_address, server)
        
    def log_message(self, format, *args):
        pass # 隱藏 log
        
    def do_GET(self):
        url = urlparse(self.path)
        
        if url.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
            
        elif url.path == '/image':
            if os.path.exists(self.image_path):
                self.send_response(200)
                # 根據附檔名決定 content-type
                ext = os.path.splitext(self.image_path)[1].lower()
                ctype = 'image/jpeg'
                if ext == '.png': ctype = 'image/png'
                elif ext == '.gif': ctype = 'image/gif'
                
                self.send_header('Content-type', ctype)
                self.end_headers()
                with open(self.image_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
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
            
            self.result_callback(results)
            threading.Thread(target=self.server.shutdown).start()

def start_crop_review(image_path):
    """
    開啟 Web UI 進行單張照片的裁切審查
    回傳 dict: {"x": int, "y": int, "width": int, "height": int}
    """
    final_result = None
    
    def on_result(result):
        nonlocal final_result
        final_result = result
        
    def handler_factory(*args, **kwargs):
        return CropReviewHandler(*args, image_path=image_path, result_callback=on_result, **kwargs)
        
    server = None
    port = 8086
    for p in range(8086, 8096):
        try:
            HTTPServer.allow_reuse_address = True
            server = HTTPServer(('127.0.0.1', p), handler_factory)
            port = p
            break
        except OSError:
            continue
            
    if server is None:
        print("[錯誤] 無法啟動裁切 Web UI，所有連接埠皆被佔用。")
        return None

    print("\n" + "="*60)
    print(" [Web 裁切模式啟動]")
    print(f" 伺服器運行於: http://127.0.0.1:{port}")
    print(" 正在為您自動打開瀏覽器...")
    print(" 請在網頁上設定您想要的裁切範圍，完成後點擊「儲存並套用至所有照片」")
    print("="*60 + "\n")
    
    webbrowser.open(f"http://127.0.0.1:{port}")
    
    # 阻塞直到 server 被 shutdown
    server.serve_forever()
    server.server_close()
    
    return final_result
