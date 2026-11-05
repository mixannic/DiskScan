#!/usr/bin/env python3
"""
Анализатор дискового пространства.
Кроссплатформенное приложение (Windows, Linux) с GUI на Tkinter.
Отображает иерархию папок с рекурсивными размерами, позволяет быстро
находить крупные каталоги и файлы.
"""
import os
import sys
import stat
import string
import threading
import queue
import time
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
from collections import defaultdict

# ------------------------------------------------------------
# Вспомогательные функции
# ------------------------------------------------------------
def format_size(size_bytes: int) -> str:
    """Форматирует размер в читаемый вид."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    for unit in ('KB', 'MB', 'GB', 'TB', 'PB'):
        size_bytes /= 1024.0
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
    return f"{size_bytes:.1f} PB"

def format_timestamp(ts: float) -> str:
    """Преобразует timestamp в строку."""
    if ts == 0:
        return "—"
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return "—"

def get_drives() -> list:
    """Возвращает список доступных локальных/съёмных дисков."""
    drives = []
    if sys.platform == "win32":
        import ctypes
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drives.append(f"{letter}:\\")
            bitmask >>= 1
    else:
        # Linux / macOS
        drives.append("/")
        # Добавляем типичные точки монтирования
        for base in ("/media", "/mnt"):
            if os.path.isdir(base):
                try:
                    for entry in os.listdir(base):
                        full = os.path.join(base, entry)
                        if os.path.isdir(full) and os.path.ismount(full):
                            drives.append(full)
                except PermissionError:
                    pass
    return sorted(drives)

def get_folder_date(path: str) -> float:
    """Получить дату папки (предпочитаем время создания, если доступно)."""
    try:
        st = os.stat(path)
        # birthtime доступен начиная с Python 3.12 на некоторых ОС
        if hasattr(st, 'st_birthtime'):
            return st.st_birthtime
        # На Windows ctime — время создания
        if sys.platform == "win32":
            return st.st_ctime
        # На Linux ctime — время изменения метаданных, mtime — изменения содержимого.
        # Возвращаем mtime как наиболее близкое к "дате папки".
        return st.st_mtime
    except OSError:
        return 0.0

def open_in_explorer(path: str) -> None:
    """Открывает папку или папку, содержащую файл, в системном проводнике."""
    if os.path.isdir(path):
        target_dir = path
        file_to_select = ""
    else:
        target_dir = os.path.dirname(path)
        file_to_select = path

    if sys.platform == "win32":
        if file_to_select:
            subprocess.Popen(['explorer', '/select,', file_to_select])
        else:
            subprocess.Popen(['explorer', target_dir])
    else:
        # Linux: открываем папку, выделение файла не гарантировано
        subprocess.Popen(['xdg-open', target_dir])

# ------------------------------------------------------------
# Главный класс приложения
# ------------------------------------------------------------
class DiskScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Анализатор дискового пространства")
        self.root.geometry("1200x700")
        self.root.minsize(800, 500)

        # Данные сканирования: path -> {'size': int, 'date': float, 'dirs': [str]}
        self.tree_data = {}
        # Маппинг: path -> iid элемента в Treeview
        self.node_map = {}
        # Очередь для безопасного обновления UI из рабочего потока
        self.gui_queue = queue.Queue()
        # Поток сканирования
        self.scan_thread = None
        self.scan_running = False
        self.scan_stop_requested = False

        # Переменные для прогресса
        self.total_objects = 0
        self.processed_objects = 0
        self.lock = threading.Lock()

        # Текущий выбранный путь в левой панели
        self.current_left_path = None

        # Создаём интерфейс
        self.setup_ui()

        # Запускаем обработчик очереди UI
        self.process_gui_queue()

        # Загружаем список дисков
        self.refresh_drive_list()

    def setup_ui(self):
        # ----- Верхняя панель -----
        top_frame = ttk.Frame(self.root, padding="5")
        top_frame.pack(fill=tk.X, side=tk.TOP)

        ttk.Label(top_frame, text="Диск:").pack(side=tk.LEFT, padx=(0,5))
        self.drive_var = tk.StringVar()
        self.drive_combo = ttk.Combobox(top_frame, textvariable=self.drive_var,
                                        state="readonly", width=30)
        self.drive_combo.pack(side=tk.LEFT, padx=(0,10))

        self.scan_btn = ttk.Button(top_frame, text="Сканировать", command=self.start_scan)
        self.scan_btn.pack(side=tk.LEFT, padx=(0,10))

        self.stop_btn = ttk.Button(top_frame, text="Остановить", command=self.stop_scan,
                                   state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(0,10))

        self.progress = ttk.Progressbar(top_frame, mode='determinate', length=300)
        self.progress.pack(side=tk.LEFT, padx=(10,10))

        self.status_label = ttk.Label(top_frame, text="Готов", width=30)
        self.status_label.pack(side=tk.LEFT)

        # ----- Горизонтальный PanedWindow для двух нижних областей -----
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Левая панель: Папки
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        # Элементы управления сортировкой папок
        sort_frame = ttk.Frame(left_frame)
        sort_frame.pack(fill=tk.X, pady=(0,3))
        ttk.Label(sort_frame, text="Сортировка:").pack(side=tk.LEFT, padx=(0,5))
        self.folder_sort_var = tk.StringVar(value="name")
        ttk.Radiobutton(sort_frame, text="Имя", variable=self.folder_sort_var,
                        value="name", command=self.on_folder_sort_changed).pack(side=tk.LEFT)
        ttk.Radiobutton(sort_frame, text="Размер", variable=self.folder_sort_var,
                        value="size", command=self.on_folder_sort_changed).pack(side=tk.LEFT)
        ttk.Radiobutton(sort_frame, text="Дата", variable=self.folder_sort_var,
                        value="date", command=self.on_folder_sort_changed).pack(side=tk.LEFT)

        # Treeview для папок
        self.folder_tree = ttk.Treeview(left_frame, columns=("size", "date"),
                                        displaycolumns=("size", "date"),
                                        selectmode="browse")
        self.folder_tree.heading("#0", text="Папка", anchor=tk.W)
        self.folder_tree.heading("size", text="Размер", anchor=tk.E,
                                 command=lambda: self.sort_folder_tree_by("size"))
        self.folder_tree.heading("date", text="Дата", anchor=tk.W,
                                 command=lambda: self.sort_folder_tree_by("date"))
        self.folder_tree.column("#0", width=250, stretch=True)
        self.folder_tree.column("size", width=100, anchor=tk.E, stretch=False)
        self.folder_tree.column("date", width=130, anchor=tk.W, stretch=False)

        # Вертикальный скроллбар
        v_scroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL, command=self.folder_tree.yview)
        self.folder_tree.configure(yscrollcommand=v_scroll.set)
        self.folder_tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        v_scroll.pack(fill=tk.Y, side=tk.RIGHT)

        # События дерева
        self.folder_tree.bind("<<TreeviewOpen>>", self.on_tree_open)
        self.folder_tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # Правая панель: Файлы
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)

        # Верхняя строка фильтров и выбора даты
        filter_bar = ttk.Frame(right_frame)
        filter_bar.pack(fill=tk.X, pady=(0,3))

        ttk.Label(filter_bar, text="Имя:").pack(side=tk.LEFT, padx=(0,3))
        self.filter_name_var = tk.StringVar()
        self.filter_name_entry = ttk.Entry(filter_bar, textvariable=self.filter_name_var, width=15)
        self.filter_name_entry.pack(side=tk.LEFT, padx=(0,5))

        ttk.Label(filter_bar, text="Размер(MB) от:").pack(side=tk.LEFT, padx=(0,3))
        self.filter_size_from_var = tk.StringVar()
        self.filter_size_from_entry = ttk.Entry(filter_bar, textvariable=self.filter_size_from_var,
                                                width=8)
        self.filter_size_from_entry.pack(side=tk.LEFT, padx=(0,3))

        ttk.Label(filter_bar, text="до:").pack(side=tk.LEFT, padx=(0,3))
        self.filter_size_to_var = tk.StringVar()
        self.filter_size_to_entry = ttk.Entry(filter_bar, textvariable=self.filter_size_to_var,
                                              width=8)
        self.filter_size_to_entry.pack(side=tk.LEFT, padx=(0,5))

        self.apply_filter_btn = ttk.Button(filter_bar, text="Применить",
                                           command=self.apply_file_filter)
        self.apply_filter_btn.pack(side=tk.LEFT, padx=(0,10))

        ttk.Label(filter_bar, text="Дата:").pack(side=tk.LEFT, padx=(0,3))
        self.date_type_var = tk.StringVar(value="ctime")
        date_combo = ttk.Combobox(filter_bar, textvariable=self.date_type_var,
                                  values=("ctime", "mtime", "atime"), state="readonly", width=8)
        date_combo.pack(side=tk.LEFT, padx=(0,5))
        date_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_file_filter())

        self.open_explorer_btn = ttk.Button(filter_bar, text="Открыть в проводнике",
                                            command=self.open_selected_in_explorer)
        self.open_explorer_btn.pack(side=tk.LEFT)

        # Таблица файлов
        self.file_table = ttk.Treeview(right_frame,
                                       columns=("name", "size", "path", "date"),
                                       selectmode="extended")
        self.file_table.heading("name", text="Имя", anchor=tk.W,
                                command=lambda: self.sort_file_table_by("name"))
        self.file_table.heading("size", text="Размер", anchor=tk.E,
                                command=lambda: self.sort_file_table_by("size"))
        self.file_table.heading("path", text="Путь", anchor=tk.W,
                                command=lambda: self.sort_file_table_by("path"))
        self.file_table.heading("date", text="Дата", anchor=tk.W,
                                command=lambda: self.sort_file_table_by("date"))
        self.file_table.column("name", width=200, stretch=True)
        self.file_table.column("size", width=100, anchor=tk.E, stretch=False)
        self.file_table.column("path", width=300, stretch=True)
        self.file_table.column("date", width=130, anchor=tk.W, stretch=False)

        self.file_table["displaycolumns"] = ("name", "size", "path", "date")

        # Скроллбары для таблицы файлов
        file_v_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL,
                                      command=self.file_table.yview)
        file_h_scroll = ttk.Scrollbar(right_frame, orient=tk.HORIZONTAL,
                                      command=self.file_table.xview)
        self.file_table.configure(yscrollcommand=file_v_scroll.set,
                                  xscrollcommand=file_h_scroll.set)
        self.file_table.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        file_v_scroll.pack(fill=tk.Y, side=tk.RIGHT)
        file_h_scroll.pack(fill=tk.X, side=tk.BOTTOM)

        # Хранилище полных данных для отображаемой папки (до фильтрации)
        self.current_files_data = []   # список словарей {name,size,path,date,is_dir}
        self.file_sort_column = "name"
        self.file_sort_reverse = False

    # --------------------------------------------------------
    # Управление дисками и запуск сканирования
    # --------------------------------------------------------
    def refresh_drive_list(self):
        drives = get_drives()
        self.drive_combo['values'] = drives
        if drives:
            self.drive_var.set(drives[0])

    def start_scan(self):
        if self.scan_running:
            messagebox.showwarning("Сканирование", "Сканирование уже выполняется.")
            return
        drive = self.drive_var.get()
        if not drive or not os.path.exists(drive):
            messagebox.showerror("Ошибка", "Выберите существующий диск.")
            return

        # Очистка предыдущих данных
        self.tree_data.clear()
        self.node_map.clear()
        self.folder_tree.delete(*self.folder_tree.get_children())
        self.file_table.delete(*self.file_table.get_children())
        self.current_files_data.clear()

        self.scan_running = True
        self.scan_stop_requested = False
        self.scan_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress['value'] = 0
        self.progress['mode'] = 'indeterminate'
        self.progress.start(20)
        self.status_label.config(text="Подсчёт объектов...")

        # Запуск в отдельном потоке
        self.scan_thread = threading.Thread(target=self.scan_drive, args=(drive,),
                                            daemon=True)
        self.scan_thread.start()

    def stop_scan(self):
        if self.scan_running:
            self.scan_stop_requested = True
            self.status_label.config(text="Остановка...")

    def scan_drive(self, root_path):
        """
        Двухпроходное сканирование:
        1) Быстрый подсчёт количества файлов/папок.
        2) Рекурсивный обход с вычислением размеров и обновлением UI.
        """
        try:
            # Первый проход – подсчёт объектов
            total = 0
            self.status_label.config(text="Подсчёт объектов...")
            for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False,
                                                        onerror=lambda e: None):
                if self.scan_stop_requested:
                    self.gui_queue.put(('scan_finished', None))
                    return
                total += len(filenames) + len(dirnames)
                # Периодически проверяем остановку и обновляем статус
                if total % 10000 == 0:
                    self.gui_queue.put(('status', f"Подсчитано {total} объектов..."))
            with self.lock:
                self.total_objects = total
                self.processed_objects = 0

            if self.scan_stop_requested:
                self.gui_queue.put(('scan_finished', None))
                return

            # Второй проход – сканирование с размерами
            self.gui_queue.put(('status', "Сканирование..."))
            self.gui_queue.put(('progress_mode', 'determinate'))
            self.gui_queue.put(('progress_max', total))

            # Создаём корневой узел и начинаем рекурсию
            root_data = {'size': 0, 'date': get_folder_date(root_path), 'dirs': []}
            self.tree_data[root_path] = root_data
            self.gui_queue.put(('add_node', root_path, None))

            self._recursive_scan(root_path)

            if self.scan_stop_requested:
                self.gui_queue.put(('scan_finished', None))
                return

            self.gui_queue.put(('scan_finished', "Сканирование завершено"))
        except Exception as e:
            self.gui_queue.put(('error', str(e)))

    def _recursive_scan(self, path):
        """Рекурсивно обходит папку, вычисляет размеры, добавляет узлы в UI."""
        if self.scan_stop_requested:
            return 0

        total_size = 0
        subdirs = []
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if self.scan_stop_requested:
                        break
                    # Пропускаем символьные ссылки и точки соединения
                    if entry.is_symlink():
                        continue
                    if sys.platform == "win32":
                        # На Windows дополнительно проверяем junction (reparse point)
                        # через атрибуты; для простоты оставляем только is_symlink
                        pass

                    if entry.is_file():
                        try:
                            size = entry.stat().st_size
                            total_size += size
                        except OSError:
                            size = 0
                        self._increment_progress()
                    elif entry.is_dir():
                        subdir_name = entry.name
                        subdir_path = entry.path
                        # Добавляем узел для подпапки перед её обработкой
                        subdir_data = {'size': 0,
                                       'date': get_folder_date(subdir_path),
                                       'dirs': []}
                        self.tree_data[subdir_path] = subdir_data
                        self.gui_queue.put(('add_node', subdir_path, path))

                        sub_size = self._recursive_scan(subdir_path)
                        total_size += sub_size
                        subdirs.append(subdir_name)
                        # Обновляем запись подпапки
                        self.tree_data[subdir_path]['size'] = sub_size
                        self.tree_data[subdir_path]['dirs'] = []  # уже не нужны
                        # Отправляем обновление размера
                        self.gui_queue.put(('update_node', subdir_path, sub_size,
                                            self.tree_data[subdir_path]['date']))
                        self._increment_progress()  # папка как объект
        except PermissionError:
            pass
        except OSError:
            pass

        # Завершение обработки текущей папки
        if not self.scan_stop_requested:
            self.tree_data[path]['size'] = total_size
            self.tree_data[path]['dirs'] = subdirs
            self.gui_queue.put(('update_node', path, total_size,
                                self.tree_data[path]['date']))
        return total_size

    def _increment_progress(self):
        with self.lock:
            self.processed_objects += 1
            cnt = self.processed_objects
        if cnt % 500 == 0:   # обновляем прогресс порциями, чтобы не спамить очередь
            self.gui_queue.put(('progress', cnt))

    # --------------------------------------------------------
    # Обработка очереди сообщений в основном потоке
    # --------------------------------------------------------
    def process_gui_queue(self):
        try:
            while True:
                msg = self.gui_queue.get_nowait()
                action = msg[0]
                if action == 'progress':
                    value = msg[1]
                    self.progress['value'] = value
                elif action == 'progress_mode':
                    mode = msg[1]
                    self.progress['mode'] = mode
                    if mode == 'indeterminate':
                        self.progress.start(20)
                    else:
                        self.progress.stop()
                elif action == 'progress_max':
                    self.progress['maximum'] = msg[1]
                elif action == 'status':
                    self.status_label.config(text=msg[1])
                elif action == 'add_node':
                    path, parent_path = msg[1], msg[2]
                    self._add_folder_node(path, parent_path)
                elif action == 'update_node':
                    path, size, date = msg[1], msg[2], msg[3]
                    self._update_folder_node(path, size, date)
                elif action == 'scan_finished':
                    self._on_scan_finished(msg[1] if len(msg) > 1 else None)
                elif action == 'error':
                    messagebox.showerror("Ошибка сканирования", msg[1])
                    self._on_scan_finished(None)
        except queue.Empty:
            pass
        # Планируем следующий опрос
        self.root.after(100, self.process_gui_queue)

    def _add_folder_node(self, path, parent_path):
        """Добавляет узел папки в дерево (если ещё нет)."""
        if path in self.node_map:
            return
        name = os.path.basename(path) or path  # для корня типа "C:\" или "/"
        date_str = format_timestamp(self.tree_data[path]['date'])
        size_str = format_size(0)  # изначально 0

        # Определяем родительский iid
        parent_iid = self.node_map.get(parent_path, "") if parent_path else ""

        # Вставляем в дерево
        iid = self.folder_tree.insert(parent_iid, tk.END, text=name,
                                      values=(size_str, date_str))
        self.node_map[path] = iid

        # Если родитель уже раскрыт, то этот новый узел автоматически появится.
        # Но если родитель ещё не раскрывался, узел будет скрыт (это нормально,
        # появится при раскрытии).

    def _update_folder_node(self, path, size, date):
        """Обновляет размер и дату узла."""
        iid = self.node_map.get(path)
        if iid:
            size_str = format_size(size)
            date_str = format_timestamp(date)
            self.folder_tree.item(iid, values=(size_str, date_str))

    def _on_scan_finished(self, message):
        self.scan_running = False
        self.scan_thread = None
        self.scan_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.progress.stop()
        self.progress['mode'] = 'determinate'
        self.progress['value'] = 0
        self.status_label.config(text=message or "Готов")
        # После завершения можно принудительно обновить корневой узел (уже обновлён)
        # и попытаться открыть корень в дереве
        if self.tree_data:
            root_path = next(iter(self.tree_data))
            # Раскрываем корневой узел (запустит ленивую загрузку)
            root_iid = self.node_map.get(root_path)
            if root_iid:
                self.folder_tree.see(root_iid)
                self.folder_tree.focus(root_iid)
                self.folder_tree.selection_set(root_iid)
                # Раскрываем один уровень вниз
                self.folder_tree.item(root_iid, open=True)

    # --------------------------------------------------------
    # Логика левого дерева (папки)
    # --------------------------------------------------------
    def on_tree_open(self, event):
        """Ленивая загрузка подпапок при раскрытии узла."""
        iid = self.folder_tree.focus()
        if not iid:
            return
        # Находим путь, соответствующий этому iid
        path = None
        for p, i in self.node_map.items():
            if i == iid:
                path = p
                break
        if not path or path not in self.tree_data:
            return

        # Если у узла уже есть дети, ничего не делаем (уже загружены)
        if self.folder_tree.get_children(iid):
            return

        # Добавляем дочерние папки из self.tree_data[path]['dirs']
        dirs = self.tree_data[path].get('dirs', [])
        # Сортируем согласно текущей настройке
        sort_key = self.folder_sort_var.get()
        children = []
        for dname in dirs:
            child_path = os.path.join(path, dname)
            if child_path in self.tree_data:
                children.append((dname, child_path, self.tree_data[child_path]))
        # Сортировка
        if sort_key == "size":
            children.sort(key=lambda x: x[2]['size'], reverse=True)
        elif sort_key == "date":
            children.sort(key=lambda x: x[2]['date'], reverse=True)
        else:  # name
            children.sort(key=lambda x: x[0].lower())

        # Вставляем отсортированные узлы
        for dname, cpath, cdata in children:
            if cpath not in self.node_map:  # мог быть уже добавлен при сканировании
                date_str = format_timestamp(cdata['date'])
                size_str = format_size(cdata['size'])
                child_iid = self.folder_tree.insert(iid, tk.END, text=dname,
                                                    values=(size_str, date_str))
                self.node_map[cpath] = child_iid
        # Удаляем временный список dirs после первого раскрытия (экономия памяти)
        # self.tree_data[path]['dirs'] = []  # можно оставить для последующей перезагрузки сортировки

    def on_tree_select(self, event):
        """При выборе папки в дереве обновляем правую таблицу."""
        iid = self.folder_tree.selection()
        if not iid:
            return
        iid = iid[0]
        path = self._get_path_by_iid(iid)
        if not path:
            return
        self.current_left_path = path
        self.populate_file_table(path)

    def _get_path_by_iid(self, iid):
        for p, i in self.node_map.items():
            if i == iid:
                return p
        return None

    def on_folder_sort_changed(self):
        """Изменение критерия сортировки папок – перестраиваем открытые узлы."""
        # Удаляем всех детей у раскрытых узлов и перезагружаем через on_tree_open
        for path, iid in self.node_map.items():
            if self.folder_tree.get_children(iid):
                # Удаляем только дочерние элементы, сам узел оставляем
                for child in self.folder_tree.get_children(iid):
                    self.folder_tree.delete(child)
                # Удаляем эти дочерние пути из node_map
                # Проще: перебрать node_map и удалить те, чей родитель path
                to_remove = [cp for cp, ci in self.node_map.items()
                             if ci != iid and os.path.dirname(cp) == path]
                for cp in to_remove:
                    del self.node_map[cp]
                # Теперь инициируем ленивую загрузку заново
                self.folder_tree.item(iid, open=False)
                self.folder_tree.item(iid, open=True)

    def sort_folder_tree_by(self, column):
        # Переключение сортировки по клику на заголовок
        current = self.folder_sort_var.get()
        if column == "size":
            new = "name" if current == "size" else "size"
        elif column == "date":
            new = "name" if current == "date" else "date"
        else:
            new = "name"
        self.folder_sort_var.set(new)
        self.on_folder_sort_changed()

    # --------------------------------------------------------
    # Правая таблица (файлы и подпапки выбранной папки)
    # --------------------------------------------------------
    def populate_file_table(self, folder_path):
        """Заполняет таблицу файлов содержимым folder_path."""
        self.file_table.delete(*self.file_table.get_children())
        self.current_files_data.clear()

        if not folder_path or folder_path not in self.tree_data:
            return

        # Собираем прямые дочерние элементы (файлы и папки) через os.scandir
        try:
            with os.scandir(folder_path) as it:
                for entry in it:
                    if entry.is_symlink():
                        continue
                    try:
                        stat = entry.stat()
                    except OSError:
                        continue

                    if entry.is_file():
                        size = stat.st_size
                        is_dir = False
                    elif entry.is_dir():
                        # Для папки берём рекурсивный размер из tree_data, если доступен
                        sub_path = entry.path
                        size = self.tree_data.get(sub_path, {}).get('size', 0)
                        is_dir = True
                    else:
                        continue

                    # Дата в зависимости от выбора
                    date_ts = self._get_date_by_type(stat)
                    self.current_files_data.append({
                        'name': entry.name,
                        'size': size,
                        'path': entry.path,
                        'date': date_ts,
                        'is_dir': is_dir
                    })
        except PermissionError:
            pass
        except OSError:
            pass

        # Применяем фильтр и сортировку
        self.apply_file_filter()

    def _get_date_by_type(self, stat):
        """Возвращает timestamp согласно выбранному типу даты."""
        dtype = self.date_type_var.get()
        if dtype == "mtime":
            return stat.st_mtime
        elif dtype == "atime":
            return stat.st_atime
        else:  # ctime (создание или изменение атрибутов)
            if hasattr(stat, 'st_birthtime'):
                return stat.st_birthtime
            return stat.st_ctime

    def apply_file_filter(self):
        """Применяет фильтр и сортировку к данным правой таблицы."""
        # Собираем фильтры
        name_filter = self.filter_name_var.get().strip().lower()
        size_from = self._parse_size_mb(self.filter_size_from_var.get())
        size_to = self._parse_size_mb(self.filter_size_to_var.get())

        filtered = []
        for item in self.current_files_data:
            # Фильтр по имени
            if name_filter and name_filter not in item['name'].lower():
                continue
            # Фильтр по размеру
            size_mb = item['size'] / (1024*1024)
            if size_from is not None and size_mb < size_from:
                continue
            if size_to is not None and size_mb > size_to:
                continue
            filtered.append(item)

        # Сортировка
        sort_col = self.file_sort_column
        reverse = self.file_sort_reverse
        if sort_col == "size":
            filtered.sort(key=lambda x: x['size'], reverse=reverse)
        elif sort_col == "date":
            filtered.sort(key=lambda x: x['date'], reverse=reverse)
        elif sort_col == "path":
            filtered.sort(key=lambda x: x['path'], reverse=reverse)
        else:  # name
            filtered.sort(key=lambda x: x['name'].lower(), reverse=reverse)

        # Заполняем таблицу
        self.file_table.delete(*self.file_table.get_children())
        for item in filtered:
            size_str = format_size(item['size'])
            date_str = format_timestamp(item['date'])
            name_display = f"📁 {item['name']}" if item['is_dir'] else item['name']
            self.file_table.insert("", tk.END,
                                   values=(name_display, size_str, item['path'], date_str),
                                   tags=("dir" if item['is_dir'] else "file",))
        # Настройка цветов
        self.file_table.tag_configure("dir", foreground="blue")

    def _parse_size_mb(self, s):
        """Преобразует строку в мегабайты (float) или None."""
        if not s.strip():
            return None
        try:
            return float(s)
        except ValueError:
            return None

    def sort_file_table_by(self, column):
        """Обработчик клика по заголовку правой таблицы."""
        if self.file_sort_column == column:
            self.file_sort_reverse = not self.file_sort_reverse
        else:
            self.file_sort_column = column
            self.file_sort_reverse = False
        self.apply_file_filter()

    def open_selected_in_explorer(self):
        """Открывает выбранный элемент в проводнике."""
        selection = self.file_table.selection()
        if not selection:
            messagebox.showinfo("Информация", "Выберите файл или папку в таблице.")
            return
        # Можно открыть несколько, но откроем первый
        item = self.file_table.item(selection[0])
        values = item['values']
        if values and len(values) >= 3:
            path = values[2]  # путь в третьей колонке
            if os.path.exists(path):
                open_in_explorer(path)
            else:
                messagebox.showerror("Ошибка", "Путь не существует.")

    # --------------------------------------------------------
    # Завершение работы
    # --------------------------------------------------------
    def on_closing(self):
        self.scan_stop_requested = True
        if self.scan_thread and self.scan_thread.is_alive():
            self.scan_thread.join(timeout=1.0)
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = DiskScannerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()