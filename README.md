# DiskScan — Disk Space Analyzer / Анализатор дискового пространства

> Cross-platform desktop application (Windows / Linux) with a Tkinter GUI for analyzing used disk space. Quickly find large folders and files, browse directory hierarchies with recursive sizes, and apply filters.
>
> Кроссплатформенное десктопное приложение (Windows / Linux) с графическим интерфейсом на Tkinter для анализа занятого дискового пространства. Быстро находите крупные папки и файлы, просматривайте иерархию каталогов с рекурсивными размерами и применяйте фильтры.

---

## Features / Возможности

| English | Русский |
|---------|---------|
| Automatic detection of local and removable drives | Автоопределение локальных и съёмных дисков |
| Recursive folder size calculation | Рекурсивный расчёт размера папок |
| Two-pass scanning with progress bar (count objects → scan with sizes) | Двухпроходное сканирование с индикатором прогресса (подсчёт объектов → сканирование с размерами) |
| Stop scanning at any time | Возможность остановки сканирования в любой момент |
| Left panel: folder tree with lazy loading; sort by name / size / date | Левая панель: дерево папок с ленивой загрузкой и сортировкой по имени / размеру / дате |
| Right panel: files and subfolders table with sortable columns | Правая панель: таблица файлов и подпапок выбранной папки с sortable колонками |
| Filter by name, size range (from/to in MB), date type (ctime / mtime / atime) | Фильтрация файлов по имени, диапазону размера (от/до в МБ) и типу даты (ctime / mtime / atime) |
| Open selected item in system Explorer (`explorer` on Windows, `xdg-open` on Linux) | Открытие выбранного элемента в системном проводнике (`explorer` на Windows, `xdg-open` на Linux) |
| Skips symbolic links and junction points | Пропуск символических ссылок и точек соединения |
| Handles `PermissionError` / `OSError` without crashing | Обработка ошибок доступа (`PermissionError`, `OSError`) без прерывания работы |
| Supports folder creation/change time (birthtime, ctime, mtime depending on OS) | Поддержка времени создания/изменения папки (birthtime, ctime, mtime в зависимости от ОС) |

---

## Requirements / Требования

- **Python 3** (recommended 3.8+) / **Python 3** (рекомендуется 3.8+)
- **Python Standard Library only** (`tkinter`, `os`, `threading`, `queue`, `ctypes`, etc.) / **Только стандартная библиотека Python** (`tkinter`, `os`, `threading`, `queue`, `ctypes` и др.)
- **No external dependencies** / **Внешних зависимостей нет**

---

## Quick Start / Быстрый старт

### From source / Из исходного кода

```bash
# Clone the repository / Клонируйте репозиторий
git clone https://github.com/mixannic/DiskScan.git
cd DiskScan

# Run the application / Запустите приложение
python diskscan.py
```

### Pre-built executable / Готовый исполняемый файл (Windows)

A ready-to-run Windows executable is available in the **Releases** section of this repository:

Готовый исполняемый файл для Windows доступен в разделе **Releases** этого репозитория:

- **File:** `Анализатор дискового пространства.exe` (~8.2 MB)
- **Packaged with:** PyInstaller (single-file, windowed, no console)
- **No Python installation required** / Не требует установки Python

Simply download the `.exe` from the latest Release and run it.

Просто скачайте `.exe` из последнего Releases и запустите его.

---

## Project Structure / Структура проекта

```
DiskScan/
├── diskscan.py                              # Main application script / Основной скрипт приложения
├── Анализатор дискового пространства.spec   # PyInstaller spec file / Файл спецификации PyInstaller
├── README.md                                # This file / Этот файл
├── LICENSE                                  # MIT License / Лицензия MIT
└── .gitignore                               # Git ignored files / Игнорируемые файлы Git
```

> The compiled `dist\Анализатор дискового пространства.exe` (~8.2 MB) is distributed via GitHub Releases and is **not** committed to the repository.
>
> Собранный `dist\Анализатор дискового пространства.exe` (~8.2 МБ) распространяется через GitHub Releases и **не** фиксируется в репозитории.

---

## Usage / Использование

1. Select a drive from the dropdown and click **Scan** / Выберите диск в выпадающем списке и нажмите **Сканировать**.
2. Wait for scanning to finish (or click **Stop**) / Дождитесь завершения сканирования (или нажмите **Остановить**).
3. In the left panel, expand folders to see their recursive size / В левой панели раскрывайте папки, чтобы увидеть их рекурсивный размер.
4. Select a folder — the right table shows its files and subfolders / Выберите папку — в правой таблице отобразятся её файлы и подпапки.
5. Use the filter fields (name, size from/to, date type) and click **Apply** / Используйте поля фильтра (имя, размер от/до, тип даты) и нажмите **Применить**.
6. Select a row and click **Open in Explorer** to open the item in the system / Дважды кликните или выберите строку и нажмите **Открыть в проводнике**, чтобы открыть элемент в системе.

---

## Rebuilding the EXE / Пересборка EXE

The application is packaged with **PyInstaller**. The `.spec` file is included in the repository for reproducible builds.

Приложение упаковано с помощью **PyInstaller**. Файл `.spec` включён в репозиторий для воспроизводимой сборки.

```bash
# Install PyInstaller / Установите PyInstaller
pip install pyinstaller

# Build the executable / Соберите исполняемый файл
pyinstaller "Анализатор дискового пространства.spec"
```

The output will appear in `dist\Анализатор дискового пространства.exe`.

Результат появится в `dist\Анализатор дискового пространства.exe`.

---

## License / Лицензия

Distributed under the **MIT** license. See the `LICENSE` file. / Распространяется под лицензией **MIT**. См. файл `LICENSE`.

---

## Roadmap / Планы развития

- Split into modules (`ui`, `scanner`, `utils`) / Разбиение на модули
- Unit tests (pytest / unittest) / Тесты
- Save settings and scan history / Сохранение настроек и истории сканирований
- Dark theme, export report (CSV / JSON) / Тёмная тема, экспорт отчёта (CSV / JSON)
