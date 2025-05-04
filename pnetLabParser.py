import base64
import hashlib
import re
import uuid
import json
import argparse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from bs4 import BeautifulSoup


@dataclass
class TemplateParams:
    template_path: Path  # Выбор файла шаблона
    lab_name: str  # Название лаболаторной без .unl
    telnet_links: dict[str, str]  # Адрес для устройства node JSON формата
    debug: bool  # Debug режим (True для проверки HTML результата)


def select_template_file() -> Path | None:
    import tkinter as tk
    from tkinter import filedialog
    """Выбор файла шаблона через проводник"""
    root = tk.Tk()
    root.withdraw()  # Скрываем основное окно

    # Настраиваем диалог выбора файла
    initial_dir = Path(__file__).parent / "templates"
    file_path = filedialog.askopenfilename(
        title="Выберите HTML шаблон лабораторной работы",
        initialdir=str(initial_dir),
        filetypes=[("HTML files", "*.html")]
    )

    return Path(file_path) if file_path else None


def create_lab_xml(lab_name: str, physical_topology_base64: str) -> bytes:
    """Создание UNL-файла с топологией"""
    guid = str(uuid.uuid4())
    lab = ET.Element("lab", {
        "name": lab_name,
        "id": guid,
        "version": "1",
        "scripttimeout": "300",
        "password": hashlib.md5(guid.encode()).hexdigest(),
        "author": "1",
        "countdown": "60",
        "darkmode": "",
        "mode3d": "",
        "nogrid": "",
        "joinable": "2",
        "joinable_emails": "admin",
        "openable": "2",
        "openable_emails": "admin",
        "editable": "2",
        "editable_emails": "admin",
        "multi_config_active": ""
    })

    ET.SubElement(lab, "topology")
    objects = ET.SubElement(lab, "objects")
    textobjects = ET.SubElement(objects, "textobjects")
    textobject = ET.SubElement(textobjects, "textobject", {
        "id": "physical-topology",
        "name": "physical",
        "type": "text"
    })
    data = ET.SubElement(textobject, "data")
    data.text = physical_topology_base64
    ET.SubElement(lab, "workbooks")

    return ET.tostring(lab, xml_declaration=True, encoding='utf-8')


def clean_html_content(content: str) -> str:
    """Очистка HTML контента"""
    content = re.sub(r'[\r\n\t]+', ' ', content)
    content = re.sub(r'[ ]{2,}', ' ', content)
    return content.strip().replace(" ", "")


def get_telnet_links(node_count: int) -> dict[str, str]:
    """Запрашиваем telnet-ссылки для устройств с иконками"""
    print("\nВведите telnet-адреса для устройств (формат: ip:port)")
    print("Пример: 10.40.83.2:2027\n")

    links = {}
    for i in range(1, node_count + 1):
        while True:
            address = input(f"Адрес для устройства node{i} (оставьте пустым если не нужно): ").strip()
            if not address:
                break
            if ":" not in address:
                print("Ошибка: используйте формат ip:port")
                continue
            links[f"node{i}"] = f"telnet://{address}"
            break
    return links


def process_template_html(content: str, links: dict[str, str]) -> str:
    """Обработка HTML с добавлением telnet-ссылок только для элементов с иконками"""
    soup = BeautifulSoup(content, 'html.parser')

    # Находим все элементы с иконками устройств
    node_icons = soup.find_all('i', {'class': 'nodehtmlconsole'})

    # Добавляем telnet-ссылки только для этих элементов
    for icon in node_icons:
        node_div = icon.find_parent('div', class_='node')
        if not node_div:
            continue

        node_id = node_div.get('id')
        if node_id and node_id in links:
            telnet_url = links[node_id]

            # 1. Добавляем onclick на всю ноду
            node_div['onclick'] = f"window.open('{telnet_url}', '_blank')"

            # 2. Меняем title у иконки
            icon['title'] = f"Telnet: {telnet_url.replace('telnet://', '')}"

            # 3. Добавляем подсказку к имени устройства
            node_name = node_div.find('div', class_='node_name')
            if node_name:
                node_name['title'] = f"Подключиться: {telnet_url}"

    # Остальная обработка (как раньше)
    lab_viewport = soup.find('div', {'id': 'lab-viewport'})
    if not lab_viewport:
        raise ValueError("Отсутствует lab-viewport в шаблоне")

    for tag in lab_viewport.find_all(attrs={"data-status": "0"}):
        del tag['data-status']
    for tag in lab_viewport.find_all(attrs={"onmousedown": True}):
        del tag['onmousedown']
    for tag in lab_viewport.find_all('div', class_='hidden'):
        tag.decompose()
    for i_tag in lab_viewport.find_all('i', class_='node_status'):
        i_tag.decompose()

    container = BeautifulSoup(features='html.parser')
    custom_div = container.new_tag('div', id='customText1',
                                   **{
                                       'class': 'customShape customText context-menu ck-content jtk-draggable dragstopped ui-selectee',
                                       'data-path': '1',
                                       'style': 'position: absolute; display: block; top: 0px; left: 0px; width: 100%; height: 100vh; z-index: 1001;'})
    container.append(custom_div)

    for child in lab_viewport.children:
        if child.name:
            custom_div.append(child)

    return str(container)


def debug_html_output(html_content: str, output_path: Path):
    import webbrowser
    """Сохранение HTML результата для отладки"""
    debug_file = output_path.with_suffix('.debug.html')
    with open(debug_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    webbrowser.open(f"file://{debug_file}")


def interface() -> TemplateParams | None:
    """Получение настроек пользователя из диалоговых окон"""
    print("=== Конвертер HTML шаблонов в UNL ===")

    # 1. Выбор файла шаблона
    template_path = select_template_file()
    if not template_path:
        print("Файл не выбран. Выход.")
        return None

    # 2. Ввод названия
    lab_name = input("Введите название лабораторной работы (без .unl): ").strip()
    if not lab_name:
        print("Название не может быть пустым!")
        return None

    try:
        # 3. Чтение шаблона и подсчет нод с иконками
        print(f"Обработка файла: {template_path.name}")
        html_content = template_path.read_text(encoding='utf-8')
        soup = BeautifulSoup(html_content, 'html.parser')

        # Считаем только ноды с иконками
        node_count = len(soup.find_all('i', {'class': 'nodehtmlconsole'}))
        print(f"Найдено устройств с иконками: {node_count}")

        # 4. Запрос telnet-адресов
        telnet_links = get_telnet_links(node_count)
    except Exception as e:
        print(f"✖ Ошибка при обработке: {str(e)}")
        return None

    return TemplateParams(
        template_path=template_path,
        lab_name=lab_name,
        telnet_links=telnet_links,
        debug=True,
    )


def cli() -> Optional[TemplateParams]:
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(
        description='Конвертер HTML шаблонов в UNL',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        '-t', '--template',
        type=str,
        help='Путь к HTML шаблону лабораторной работы'
    )
    parser.add_argument(
        '-n', '--name',
        required=True,
        type=str,
        help='Название лабораторной работы (без расширения)'
    )
    parser.add_argument(
        '-l', '--links',
        type=str,
        help='JSON строка с telnet-адресами (формат: {"node1":"ip:port", ...})'
    )
    parser.add_argument(
        '-lf', '--links-file',
        type=str,
        help='Путь к JSON-файлу с telnet-адресами'
    )
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Включить режим отладки (генерация HTML для проверки)'
    )

    args = parser.parse_args()

    try:
        # Обработка telnet-ссылок
        telnet_links = {}

        if args.links_file:
            with open(args.links_file, 'r', encoding='utf-8') as f:
                links_data = json.load(f)
                telnet_links = {k: f"telnet://{v}" if not v.startswith('telnet://') else v
                                for k, v in links_data.items()}
        elif args.links:
            links_data = json.loads(args.links)
            telnet_links = {k: f"telnet://{v}" if not v.startswith('telnet://') else v
                            for k, v in links_data.items()}

        template_path = Path(args.template) if args.template else None

        return TemplateParams(
            template_path=template_path,
            lab_name=args.name,
            telnet_links=telnet_links,
            debug=args.debug
        )
    except json.JSONDecodeError as e:
        print(f"Ошибка формата JSON: {str(e)}")
        return None
    except FileNotFoundError:
        print(f"Файл не найден: {args.links_file}")
        return None
    except Exception as e:
        print(f"Ошибка обработки аргументов: {str(e)}")
        return None


def main():
    # Парсинг аргументов CLI
    if len(sys.argv) > 1:
        params = cli()
        if not params:
            sys.exit(1)
    else:
        # Запуск GUI интерфейса если нет аргументов
        params = interface()
        if not params:
            sys.exit(0)

    try:
        # Обработка шаблона
        html_content = params.template_path.read_text(encoding='utf-8')
        processed_html = process_template_html(html_content, params.telnet_links)
        base64_content = base64.b64encode(clean_html_content(processed_html).encode("utf-8")).decode()

        # Сохранение UNL
        script_dir = Path(__file__).parent
        output_path = script_dir / f"{params.lab_name}.unl"
        output_path.write_bytes(create_lab_xml(params.lab_name, base64_content))
        print(f"✓ Файл успешно сохранён: {output_path}")

        # Отладка
        if params.debug:
            debug_html_output(processed_html, output_path)
    except Exception as e:
        print(f"✖ Ошибка при обработке: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    import sys
    main()