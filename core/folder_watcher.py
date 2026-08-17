import os
import time
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .image_loader import is_supported_image
from .batch_processor import (
    batch_process,
    load_processed_record,
    get_file_hash,
    wait_for_file_stable,
    process_product,
    scan_input_dir,
)


class InputFolderWatcher:
    def __init__(self, input_dir, output_dir, options=None, on_progress=None):
        self.input_dir = str(input_dir)
        self.output_dir = str(output_dir)
        self.options = options or {}
        self.on_progress = on_progress
        self.observer = None
        self._running = False
        self._pending_files = {}
        self._lock = threading.Lock()
        self._check_timer = None

    def start(self):
        if self._running:
            return
        self._running = True

        event_handler = _WallpaperEventHandler(self._on_file_event)
        self.observer = Observer()
        self.observer.schedule(event_handler, self.input_dir, recursive=True)
        self.observer.start()

        self._start_pending_check()

        existing = scan_input_dir(self.input_dir)
        for product in existing:
            self._process_product_async(product)

    def stop(self):
        self._running = False
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
            self.observer = None
        if self._check_timer:
            self._check_timer.cancel()
            self._check_timer = None

    def is_running(self):
        return self._running

    def _on_file_event(self, event_type, src_path):
        filename = os.path.basename(src_path)
        if filename.startswith(".") or filename.startswith("~$"):
            return
        if not is_supported_image(src_path):
            return

        with self._lock:
            self._pending_files[src_path] = time.time()

    def _start_pending_check(self):
        def check_loop():
            while self._running:
                time.sleep(2)
                self._check_pending()

        t = threading.Thread(target=check_loop, daemon=True)
        t.start()

    def _check_pending(self):
        now = time.time()
        ready = []
        with self._lock:
            for fpath, added_time in list(self._pending_files.items()):
                if now - added_time > 3:
                    try:
                        wait_for_file_stable(fpath, checks=2, interval=0.5)
                        ready.append(fpath)
                        del self._pending_files[fpath]
                    except Exception:
                        pass

        if ready:
            self._process_new_files(ready)

    def _process_new_files(self, file_paths):
        products_to_process = set()
        for fpath in file_paths:
            rel = os.path.relpath(fpath, self.input_dir)
            parts = Path(rel).parts
            if len(parts) >= 2:
                product_name = parts[0]
                products_to_process.add(product_name)
            else:
                products_to_process.add(Path(fpath).stem)

        all_products = scan_input_dir(self.input_dir)
        for p in all_products:
            if p["name"] in products_to_process:
                self._process_product_async(p)

    def _process_product_async(self, product_info):
        def worker():
            try:
                if self.on_progress:
                    self.on_progress("start", product_info["name"])
                result = process_product(product_info, self.output_dir, self.options)
                if self.on_progress:
                    self.on_progress("done", product_info["name"], result)
            except Exception as e:
                if self.on_progress:
                    self.on_progress("error", product_info["name"], {"error": str(e)})

        t = threading.Thread(target=worker, daemon=True)
        t.start()


class _WallpaperEventHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback

    def on_created(self, event):
        if not event.is_directory:
            self.callback("created", event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self.callback("modified", event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self.callback("moved", event.dest_path)
