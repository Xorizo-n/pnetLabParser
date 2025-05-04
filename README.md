# Конвертер HTML шаблонов для PNETLab

![Интерфейс](images/screenshot.png)

## 📌 О проекте
Инструмент для автоматического преобразования HTML-шаблонов сетевых топологий в формат `.unl` для использования в PNETLab

## 🚀 Примеры использования

1. Запуск GUI
`python pnetLabParser.py`
2. Запуск CLI с JSON строкой для ссылок
`python pnetLabParser.py -t templates/pnet_virtual_topology.html -n lab1 -l '{\"node1\":\"10.40.83.2:2027\",\"node2\":\"10.40.68.3:2028\",\"node3\":\"10.40.68.3:2029\",\"node4\":\"10.40.68.3:2030\",\"node5\":\"10.40.68.3:2031\",\"node6\":\"10.40.68.3:2032\"}' -d`
3. Запуск CLI с JSON файлом для ссылок
`python pnetLabParser.py -t templates/pnet_virtual_topology.html -n lab1 -lf telnet_links.json -d`

## 🛠 Настройка окружения
1. Шаблоны.
Разместите ваши HTML-файлы в папке templates/
2. Иконки устройств.
Добавьте в images/icons/ иконки, если необходимо
3. Ссылки на консоли telnet (опционально).
Создайте JSON файл со ссылками для доступа, чтобы использовать его при запуске CLI