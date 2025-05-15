import base64
import hashlib
import re
import uuid
import json
import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from bs4 import BeautifulSoup


@dataclass
class TemplateParams:
    template_path: Path
    lab_name: str
    telnet_links: Dict[str, str]
    interface_mapping: List[Dict[str, str]]
    debug: bool


def debug_log(message: str, params: TemplateParams) -> None:
    """Вывод отладочных сообщений только в режиме debug"""
    if params.debug:
        print(f"[DEBUG] {message}", file=sys.stderr)


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


def update_interfaces(soup: BeautifulSoup, interface_mapping: List[Dict[str, str]]) -> None:
    """Обновление подписей интерфейсов с учетом направления соединения"""
    # Создаем словарь для быстрого поиска интерфейсов
    interface_map = {}
    for connection in interface_mapping:
        if len(connection) != 2:
            continue
        devices = list(connection.items())
        src_node, src_iface = devices[0]
        dst_node, dst_iface = devices[1]

        interface_map[(src_node, dst_node)] = (src_iface, dst_iface)
        interface_map[(dst_node, src_node)] = (dst_iface, src_iface)

    # Обрабатываем все overlay-элементы с интерфейсами
    for overlay in soup.find_all('div', class_='jtk-overlay'):
        if 'node_interface' not in overlay.get('class', []):
            continue

        # Получаем информацию о соединении
        connector = overlay.find_parent(lambda tag: tag.has_attr('class') and 'jtk-connector' in tag.get('class'))
        if not connector:
            continue

        # Получаем имена нод из классов коннектора
        node_classes = [cls for cls in connector.get('class', [])
                        if cls.startswith('node') and cls != 'nodehtmlconsole']
        if len(node_classes) != 2:
            continue

        # Находим ноды
        node1 = soup.find('div', class_=node_classes[0])
        node2 = soup.find('div', class_=node_classes[1])
        if not node1 or not node2:
            continue

        node1_name = node1.get('data-name')
        node2_name = node2.get('data-name')
        position = overlay.get('position', '')

        # Ищем соответствующие интерфейсы в маппинге
        if (node1_name, node2_name) in interface_map:
            src_iface, dst_iface = interface_map[(node1_name, node2_name)]
            if position == 'src':
                overlay.div.string = src_iface
            elif position == 'dst':
                overlay.div.string = dst_iface


def process_template_html(content: str, params: TemplateParams) -> str:
    """Обработка HTML: очистка, telnet-ссылки, копирование, обновление интерфейсов"""
    try:
        debug_log("Начало обработки HTML шаблона", params)

        # 1. Парсинг исходного HTML
        soup = BeautifulSoup(content, 'html.parser')
        if not soup:
            raise ValueError("Не удалось разобрать HTML")

        # 2. Очистка ненужных элементов
        for element in soup.find_all(True):
            if 'data-status' in element.attrs:
                del element['data-status']
            if 'onmousedown' in element.attrs:
                del element['onmousedown']
            if element.get('class') == ['hidden']:
                element.decompose()
            if element.name == 'i' and 'node_status' in element.get('class', []):
                element.decompose()

        # 3. Обработка telnet-ссылок
        if params.telnet_links:
            debug_log(f"Обработка telnet ссылок: {params.telnet_links}", params)
            for node in soup.find_all('div', class_='node'):
                node_name = node.get('data-name', '').strip()
                telnet_url = params.telnet_links.get(node_name)
                if not node_name or not telnet_url:
                    continue

                node['style'] = f"cursor: pointer; {node.get('style', '')}"
                node['onclick'] = f"window.open('{telnet_url}', '_blank')"

                if (icon := node.find('i', class_='nodehtmlconsole')):
                    icon['title'] = f"Telnet: {telnet_url.split('://')[-1].split('/')[0]}"

                if (name_div := node.find('div', class_='node_name')):
                    name_div['title'] = f"Подключиться: {telnet_url}"

        # 4. Обновление интерфейсов
        if params.interface_mapping:
            debug_log(f"Обновление интерфейсов: {params.interface_mapping}", params)

            iface_dict = {}
            for conn in params.interface_mapping:
                if len(conn) != 2:
                    continue
                devices = list(conn.items())
                src_node, src_iface = devices[0]
                dst_node, dst_iface = devices[1]
                key = frozenset((src_node, dst_node))
                iface_dict[key] = {src_node: src_iface, dst_node: dst_iface}

            for overlay_div in soup.find_all('div', class_='node_interface'):
                position = overlay_div.get('position')

                parent = overlay_div.find_parent('div', class_='jtk-overlay')
                if not parent:
                    continue

                class_list = parent.get('class', [])
                node_classes = [cls for cls in class_list if cls.startswith('node')]
                if len(node_classes) != 2:
                    continue

                name1 = node_classes[0]
                name2 = node_classes[1]

                # Найди реальные имена узлов
                node1_div = soup.find('div', class_=name1)
                node2_div = soup.find('div', class_=name2)
                if not node1_div or not node2_div:
                    continue

                real_name1 = node1_div.get('data-name')
                real_name2 = node2_div.get('data-name')
                if not real_name1 or not real_name2:
                    continue

                conn_key = frozenset((real_name1, real_name2))
                iface_pair = iface_dict.get(conn_key)
                if not iface_pair:
                    continue

                if position == 'src':
                    overlay_div.string = iface_pair.get(real_name1, '')
                elif position == 'dst':
                    overlay_div.string = iface_pair.get(real_name2, '')

        # 5. Создание контейнера
        container = BeautifulSoup(features='html.parser')
        custom_div = container.new_tag('div', id='customText1',
                                       **{
                                           'class': 'customShape customText context-menu ck-content jtk-draggable dragstopped ui-selectee',
                                           'data-path': '1',
                                           'style': 'position: absolute; display: block; top: 0px; left: 0px; width: 100%; height: 100vh; z-index: 1001;'
                                       })
        container.append(custom_div)

        # 6. Копирование узлов
        nodes_copied = 0
        for node in soup.find_all('div', class_='node'):
            custom_div.append(node.__copy__())
            nodes_copied += 1
            debug_log(f"Скопирован узел: {node.get('id')}", params)

        # 7. Копирование соединений
        connectors_copied = 0
        for connector in soup.find_all(class_=['jtk-connector', 'jtk-endpoint', 'jtk-overlay']):
            #debug_log(f"{connector}", params)
            custom_div.append(connector.__copy__())
            connectors_copied += 1

        debug_log(f"Скопировано узлов: {nodes_copied}, соединений: {connectors_copied}", params)

        # 8. Финализация
        result = str(container)
        debug_log(f"Итоговый размер HTML: {len(result)} символов", params)

        if params.debug and params.telnet_links:
            for node_name in params.telnet_links:
                if node_name not in result:
                    debug_log(f"Внимание: узел '{node_name}' не найден в результате", params)

        return result

    except Exception as e:
        debug_log(f"Критическая ошибка обработки: {str(e)}", params)
        raise ValueError(f"Ошибка обработки HTML: {str(e)}") from e

def debug_html_output(html_content: str, output_path: Path) -> None:
    """Сохранение отладочного HTML"""
    try:
        debug_file = output_path.with_suffix('.debug.html')

        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"✓ Отладочный HTML сохранён: {debug_file.resolve()}")

        # Открываем в браузере
        import webbrowser
        webbrowser.open(f"file://{debug_file.resolve()}")

    except Exception as e:
        print(f"✖ Ошибка сохранения отладочного файла: {str(e)}", file=sys.stderr)


def parse_cli_args() -> Optional[TemplateParams]:
    """Парсинг аргументов командной строки"""
    parser = argparse.ArgumentParser(
        description='Конвертер HTML шаблонов в UNL',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '-t', '--template',
        required=True,
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
        '-lf', '--links-file',
        type=str,
        help='Путь к JSON-файлу с telnet-адресами'
    )
    parser.add_argument(
        '-imf', '--interface-mapping-file',
        type=str,
        help='Путь к JSON-файлу с маппингом интерфейсов'
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
                telnet_links = json.load(f)
        elif args.links:
            telnet_links = json.loads(args.links)

        # Нормализация telnet-ссылок
        telnet_links = {
            k: f"telnet://{v}" if not v.startswith('telnet://') else v
            for k, v in telnet_links.items()
        }

        # Обработка маппинга интерфейсов
        interface_mapping = []
        if args.interface_mapping_file:
            with open(args.interface_mapping_file, 'r', encoding='utf-8') as f:
                interface_mapping = json.load(f)
                if not isinstance(interface_mapping, list):
                    raise ValueError("Interface mapping should be a list")
        elif args.interface_mapping:
            interface_mapping = json.loads(args.interface_mapping)
            if not isinstance(interface_mapping, list):
                raise ValueError("Interface mapping should be a list")

        return TemplateParams(
            template_path=Path(args.template),
            lab_name=args.name,
            telnet_links=telnet_links,
            interface_mapping=interface_mapping,
            debug=args.debug
        )
    except json.JSONDecodeError as e:
        print(f"Ошибка формата JSON: {str(e)}")
        return None
    except FileNotFoundError as e:
        print(f"Файл не найден: {str(e)}")
        return None
    except Exception as e:
        print(f"Ошибка обработки аргументов: {str(e)}")
        return None


def main():
    # Парсинг аргументов CLI
    params = parse_cli_args()
    if not params:
        sys.exit(1)

    try:
        # Проверка существования файла шаблона
        if not params.template_path.exists():
            print(f"Файл шаблона не найден: {params.template_path}")
            sys.exit(1)

        # Чтение и обработка шаблона
        html_content = params.template_path.read_text(encoding='utf-8')
        processed_html = process_template_html(html_content, params)
        base64_content = base64.b64encode(clean_html_content(processed_html).encode("utf-8")).decode()

        # Сохранение UNL в корне проекта
        output_path = Path.cwd() / f"{params.lab_name}.unl"
        output_path.write_bytes(create_lab_xml(params.lab_name, base64_content))
        print(f"✓ UNL файл успешно сохранён: {output_path.resolve()}")

        # Отладка
        if params.debug:
            debug_path = Path.cwd()
            debug_path.mkdir(exist_ok=True)
            debug_html_output(processed_html, debug_path / f"{params.lab_name}.html")

    except Exception as e:
        print(f"✖ Ошибка при обработке: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()