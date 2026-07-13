from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout, QWidget


HELP_TEXT = """Video Event Logger: інструкція для анотаторів

Призначення

Додаток потрібен для перегляду відео та розмітки інтервалів, у яких відбувається подія. Кожен інтервал зберігається як:

start time + end time + event_type + comment

Основний сценарій

1. Натисніть Open Video і виберіть .mp4 або .mkv файл.
2. Запустіть відтворення.
3. Коли подія починається, натисніть A або кнопку Start.
4. Продовжуйте дивитися відео.
5. Коли подія завершується, натисніть D або кнопку End.
6. Якщо увімкнений popup, підтвердіть або змініть event_type і comment.
7. Продовжуйте розмічати наступні інтервали.
8. Коли робота завершена, натисніть Finish & Save JSON.

Перегляд і редагування інтервалів

- Play у рядку інтервалу відтворює відео від Start до End і автоматично ставить паузу.
- Edit у рядку інтервалу дозволяє змінити event_type і comment. Timestamp-и не редагуються.
- Delete видаляє вибраний інтервал.
- Double click по рядку переходить на Start цього інтервалу.

Клавіші

Space          Play / pause
A              Початок інтервалу
D              Кінець інтервалу
Escape         Скасувати поточний незавершений інтервал
Delete         Видалити вибраний інтервал
Left           Назад на 1 секунду
Right          Вперед на 1 секунду
Shift + Left   Назад на 10 секунд
Shift + Right  Вперед на 10 секунд
,              Назад на 1 кадр
.              Вперед на 1 кадр
1              Швидкість відтворення x1
2              Швидкість відтворення x2
4              Швидкість відтворення x4
8              Швидкість відтворення x8

event_type

Поле event_type задає тип або категорію для нових інтервалів. Після редагування натисніть Enter або зачекайте кілька секунд, поки додаток застосує значення. Якщо поле порожнє, буде використано "undefined".

Popup після інтервалу

Якщо увімкнено "Show popup after each interval", після End додаток поставить відео на паузу і попросить підтвердити event_type та додати comment. Якщо натиснути Cancel у popup, поточний інтервал не буде збережено.

Timeline scrubbing

Під час перетягування timeline додаток оновлює поточний кадр з невеликою затримкою. Це зроблено навмисно, щоб VLC не отримував занадто багато seek-команд під час швидкого drag.

Autosave і фінальне збереження

Додаток автоматично зберігає дані після створення, редагування або видалення інтервалу, а також зберігає поточну позицію відео при закритті. Autosave - це робоче збереження. Для фінального файлу використовуйте Finish & Save JSON.

Якщо для відео вже є розмітка

Якщо для вибраного відео вже є файли розмітки, додаток запропонує:

- Continue Existing Work - продовжити попередню роботу.
- Start Over - почати заново.
- Delete Project - видалити файли розмітки для цього відео.
- Cancel - скасувати відкриття.

Важливі правила

- Start має бути раніше за End.
- Якщо натиснути End без Start, інтервал не створиться.
- Якщо після Start відео було перемотано назад, перевірте, що End все ще пізніше за Start.
- У comment пишіть деталі, корисні для ревʼю. Категорію події краще тримати в event_type.
- Rotate 90 доступний тільки коли відео на паузі. Він змінює тільки перегляд у додатку. Відеофайл і timestamp-и не змінюються.
"""


class AnnotatorHelpDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Annotator Guide")
        self.resize(640, 620)

        text = QTextBrowser(self)
        text.setPlainText(HELP_TEXT)
        text.setOpenExternalLinks(False)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(text)
        layout.addWidget(buttons)
