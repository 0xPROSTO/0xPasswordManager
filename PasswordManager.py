import random
import sqlite3
import string
import sys

from PyQt6 import uic
from PyQt6.QtCore import QSettings, Qt, QTimer
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QTableWidgetItem, QDialog, QHeaderView, QLabel, QMessageBox
from cryptography.fernet import Fernet, InvalidToken

SPECIAL = ['!', '@', '#', '%', '_', '$', '~']  # Символы
DIGITS = list(str(i) for i in range(10))  # Цифры
UPPERCASE = list(string.ascii_uppercase)  # Заглавные буквы
LOWERCASE = list(string.ascii_lowercase)  # Строчные буквы


class NotAllFieldsFilled(Exception):
    pass


class NoObjectSelected(Exception):
    pass


class PasswordManagerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        uic.loadUi("UIs/PasswordManagerUI.ui", self)  # Загрузка интерфейса
        self.greeter()  # Приветствие пользователя
        self.initUI()
        self.passwordTable.sortItems(0)  # Сортировка таблицы

    def initUI(self):
        # Установка ширины для конкретных столбцов
        self.passwordTable.setColumnWidth(0, 170)  # Ширина для 1-го столбца (Сервис)
        self.passwordTable.setColumnWidth(1, 210)  # Ширина для 2-го столбца (Логин)
        self.passwordTable.setColumnWidth(2, 375)  # Ширина для 3-го столбца (Пароль)

        # Запрет на изменение размеров таблицы
        self.passwordTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.passwordTable.horizontalHeader().setStretchLastSection(True)  # Растягивание последнего столбца
        self.passwordTable.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.passwordTable.setSortingEnabled(True)  # Сортировка таблицы

        # Отключение нижней полосы прокрутки
        self.passwordTable.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Загрузка ключа шифрования
        self.encryption_key = self.load_key()

        # Загрузка данных в таблицу из БД
        self.load_passwords()
        self.passwordTable.setColumnHidden(3, True)  # Скрытие столбца с ID

        # Привязка кнопок
        self.add_button.clicked.connect(self.add_password)  # Привязка кнопки 'Добавить'
        self.gen_button.clicked.connect(self.gen_password_dialog)  # Привязка кнопки 'Сгенерировать'
        self.delete_button.clicked.connect(self.delete_password)  # Привязка кнопки 'Удалить'

        self.search_bar.textChanged.connect(self.filter_passwords)  # Привязка изменения текста строки поиска

        # Сигнал на изменение ячейки в таблице
        self.passwordTable.itemChanged.connect(self.db_update_password)

        # Добавление логотипа в углу экрана
        self.pixmap = QPixmap("logo/PasswordManager.png")
        self.image = QLabel(self)
        self.image.move(7, 5)
        self.image.resize(150, 50)
        self.image.setPixmap(self.pixmap)

        # Загрузка значка приложения
        self.setWindowIcon(QIcon('logo/icon.ico'))

        # Выключения правого нижнего угла в статусбаре
        self.statusBar().setSizeGripEnabled(False)

    def greeter(self):
        """Приветствие пользователя при входе в программу"""
        greet = random.choice(['Добро пожаловать', 'Здравствуйте', 'Добрый день',
                               'Рады видеть вас', 'С возвращением'])  # Список приветствий

        database = sqlite3.connect('passwords_db.sqlite3')
        cursor = database.cursor()

        # Список всех логинов, кроме почт
        login_list = cursor.execute("""SELECT login FROM passwords WHERE login NOT LIKE '%@%.%'""").fetchall()

        if login_list:  # Здороваемся по имени
            self.statusBar().showMessage(f'{greet}, {"".join(random.choice(login_list))}', 5000)
        else:  # Здороваемся без имени
            self.statusBar().showMessage(f'{greet}!', 5000)

    def filter_passwords(self, text):
        """фильтрация паролей по поиску"""
        try:
            for row in range(self.passwordTable.rowCount()):
                match = False
                for column in range(self.passwordTable.columnCount() - 2):  # Поиск только по сервису и логину
                    item = self.passwordTable.item(row, column)
                    if item and text.lower() in item.text().lower():  # Поиск без учета регистра
                        match = True
                        break
                self.passwordTable.setRowHidden(row, not match)  # Скрытие рядов, которые не подходят условию
        except Exception as err:
            print(err)

    def db_update_password(self, item):
        """Обновление БД при изменении ячейки"""
        try:
            row = item.row()
            column = item.column()

            if column == 3:  # Игнорирование изменения ID
                return

            # Добавление данных.strip() в таблицу
            temp = item.text().strip()  # Удаляем пробелы в начале и конце
            if temp != item.text():  # Если строка изменилась
                item.setText(temp)
                return

            service = self.passwordTable.item(row, 0).text().strip()  # Сервис
            login = self.passwordTable.item(row, 1).text().strip()  # Логин
            password = self.encrypt_password(self.passwordTable.item(row, 2).text().strip())  # Пароль
            password_id = self.passwordTable.item(row, 3).text()  # ID пароля

            if not all([service, login, self.decrypt_password(password)]):  # Проверка на отсутствие пустых полей
                raise NotAllFieldsFilled

            database = sqlite3.connect("passwords_db.sqlite3")
            cursor = database.cursor()

            # Обновление информации в БД
            cursor.execute("""UPDATE passwords SET service = ?, login = ?, password = ? 
                    WHERE id = ?""", (service, login, password, password_id))

            database.commit()  # Сохранение БД
            database.close()  # Закрытие БД

            self.statusBar().showMessage("Изменения сохранены в базе данных.", 5000)

        except NotAllFieldsFilled:
            self.statusBar().showMessage("Некоторые ячейки пустые. Изменения не сохранены.", 5000)
            self.load_passwords()  # Перезагрузка таблицы, чтобы отменить изменения

    def load_passwords(self):
        """"Загрузка информации из БД в таблицу"""
        self.passwordTable.blockSignals(True)  # Отключения сигнала на изменение ячейки
        self.passwordTable.setRowCount(0)  # Очистка таблицы

        passwords = self.db_get_all_data()  # Получение информации из БД

        # Добавление строк в таблицу
        for password in passwords:
            row_position = self.passwordTable.rowCount()
            self.passwordTable.insertRow(row_position)
            self.passwordTable.setItem(row_position, 0, QTableWidgetItem(password[1]))
            self.passwordTable.setItem(row_position, 1, QTableWidgetItem(password[2]))
            self.passwordTable.setItem(row_position, 2, QTableWidgetItem(self.decrypt_password(password[3])))
            self.passwordTable.setItem(row_position, 3, QTableWidgetItem(str(password[0])))

        self.passwordTable.blockSignals(False)  # Включение сигналов обратно

    def db_get_all_data(self):
        """Получение информации из БД"""
        try:
            database = sqlite3.connect("passwords_db.sqlite3")
            cursor = database.cursor()

            passwords = cursor.execute("SELECT * FROM passwords").fetchall()

            database.close()  # Закрытие БД
            return passwords  # Возврат полученных данных

        except Exception:  # Ошибка при загрузке БД
            message_box = QMessageBox()  # Создание мессаджбокса с уведомлением о ошибке

            # настройка message_box-а
            message_box.setIcon(QMessageBox.Icon.Warning)
            message_box.setWindowTitle('Ошибка БД (passwords_db.sqlite3)')
            message_box.setText('База данных вероятно была повреждена или удалена!\t\t\t')
            message_box.setInformativeText('Программа не может работать с неисправной БД, '
                                           'пожалуйста восстановите её или загрузите новою в дерикторию программы.')
            message_box.exec()
            sys.exit()  # закрытие приложения

    def add_password(self):
        """Добавление нового элемента в таблицу"""
        try:
            self.search_bar.setText('')
            service = self.input_service.text().strip()
            login = self.input_login.text().strip()
            password = self.encrypt_password(self.input_password.text().strip())

            if not all([service, login, self.decrypt_password(password)]):
                raise NotAllFieldsFilled

            password_id = self.db_add_password(service, login, password)

            self.passwordTable.setSortingEnabled(False)  # Временно отключаем сортировку
            new_row = self.passwordTable.rowCount()  # Определение номера нового ряда

            self.passwordTable.blockSignals(True)  # Отключения сигнала на изменение ячейки

            # Добавление ряда
            self.passwordTable.insertRow(new_row)
            self.passwordTable.setItem(new_row, 0, QTableWidgetItem(service))
            self.passwordTable.setItem(new_row, 1, QTableWidgetItem(login))
            self.passwordTable.setItem(new_row, 2, QTableWidgetItem(self.decrypt_password(password)))
            self.passwordTable.setItem(new_row, 3, QTableWidgetItem(str(password_id)))

            self.passwordTable.blockSignals(False)  # Включаем сигнал обратно

            # Очищение полей
            self.input_service.clear()
            self.input_login.clear()
            self.input_password.clear()

            self.passwordTable.setSortingEnabled(True)  # Включаем сортировку обратно

        except NotAllFieldsFilled:
            self.statusBar().showMessage('Все поля должны быть заполнены!', 5000)

    def db_add_password(self, service, login, password):
        """Добавление пароля в БД"""
        database = sqlite3.connect('passwords_db.sqlite3')
        cursor = database.cursor()

        cursor.execute("""INSERT INTO passwords (service, login, password) VALUES (?, ?, ?)""",
                       (service, login, password))

        database.commit()  # Сохранение БД
        database.close()  # Закрытие БД

        return cursor.lastrowid  # Возврат id добавленного пароля

    def gen_password_dialog(self):
        """Создаёт диалог на генератор паролей"""
        dialog = PasswordGeneratorDialog()
        if dialog.exec():  # Проверяем, был ли диалог закрыт через accept
            password_length = dialog.password_length.value()
            include_special = dialog.include_special.isChecked()
            include_digits = dialog.include_digits.isChecked()
            include_uppercase = dialog.include_uppercase.isChecked()
            include_lowercase = dialog.include_lowercase.isChecked()

            # Проверка на включённые символы
            if any([include_special, include_digits, include_uppercase, include_lowercase]):
                self.input_password.setText(self.password_generator(password_length, include_special,
                                                                    include_digits, include_uppercase,
                                                                    include_lowercase))
            else:
                self.statusBar().showMessage('Выберите хотя бы один пункт в генераторе паролей!', 5000)

    def delete_password(self, no_confirm=False):
        """Удаление элементов из таблицы"""
        try:
            selected_rows = self.passwordTable.selectionModel().selectedRows()  # Выбранные ряды

            if not selected_rows:  # Проверка, выбраны ли ряды
                raise NoObjectSelected

            if not no_confirm:  # проверка, должно ли быть подтверждение
                dialog = ConfirmDialog()  # Создание диалога подтверждения
                dialog.confirm_label.setText(f'Вы действительно хотите удалить {len(selected_rows)} '
                                             f'строк{self.word_ending(len(selected_rows))}?')

            if no_confirm or dialog.exec():  # Проверяем, был ли диалог закрыт через accept | удалён без подтверждения
                for row in sorted(selected_rows, reverse=True):  # удаление рядов
                    self.db_delete_password(self.passwordTable.item(row.row(), 3).text())  # Удаление из БД
                    self.passwordTable.removeRow(row.row())  # Удаление из таблицы
                self.statusBar().showMessage('Выбранные данные удалены!', 5000)

            else:  # Отмена удаления
                self.statusBar().showMessage('Удаление отменено', 5000)

        except NoObjectSelected:
            self.statusBar().showMessage('Выберите хотя бы 1 ряд для удаления!', 5000)

        except Exception as e:
            print(e)

    def db_delete_password(self, password_id):
        """Удаление элементов из БД"""
        database = sqlite3.connect("passwords_db.sqlite3")
        cursor = database.cursor()

        cursor.execute("""DELETE FROM passwords WHERE id = ?""", (password_id,))  # Удаление элемента

        database.commit()  # Сохранение БД
        database.close()  # Закрытие БД

    def keyPressEvent(self, event):
        """Бинды"""
        if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:  # бинд на удаление с шифтом без подтверждения
            if event.key() == Qt.Key.Key_Delete:
                self.delete_password(no_confirm=True)

        elif event.key() == Qt.Key.Key_Delete:  # бинд на обычное удаление
            self.delete_password()

        elif event.key() == Qt.Key.Key_Return:  # бинд на добавление
            self.add_password()

    def password_generator(self, length, include_special, include_digits, include_uppercase, include_lowercase):
        """Генератор паролей"""
        allowed_chars = []  # Символы, которые можно использовать
        required_chars = []  # По 1 символу из каждой выбранной категории

        # Добавление символов
        if include_special:
            allowed_chars.extend(SPECIAL)
            required_chars.append(random.choice(SPECIAL))
        if include_digits:
            allowed_chars.extend(DIGITS)
            required_chars.append(random.choice(DIGITS))
        if include_uppercase:
            allowed_chars.extend(UPPERCASE)
            required_chars.append(random.choice(UPPERCASE))
        if include_lowercase:
            allowed_chars.extend(LOWERCASE)
            required_chars.append(random.choice(LOWERCASE))

        # Создание пароля
        password = required_chars + [random.choice(allowed_chars) for _ in range(length - len(required_chars))]
        random.shuffle(password)  # Перемешивание пароля
        self.statusBar().showMessage('Пароль был успешно сгенерирован!', 5000)  # Уведомление
        return ''.join(password)

    def word_ending(self, number):
        """Выюор окончания у слова"""
        if number in range(11, 15):
            return ''
        elif number % 10 == 1:
            return 'у'
        elif number % 10 in range(2, 5):
            return 'и'
        else:
            return ''

    def generate_key(self):
        """Генерация нового ключа шифрования"""
        with open("secret.key", "wb") as f:  # Записб ключа в файл secret.key
            f.write(Fernet.generate_key())

    def load_key(self):
        """Загрузка ключа"""
        try:
            with open("secret.key", "rb") as f:
                return f.read()
        except Exception:  # Генерация нового ключа, если он отсутствует
            self.generate_key()
            return self.load_key()

    def encrypt_password(self, password):
        """Шифрование пароля"""
        return Fernet(self.encryption_key).encrypt(password.encode())

    def decrypt_password(self, password):
        """Расшифровка пароля"""
        try:
            return Fernet(self.encryption_key).decrypt(password).decode()  # Расшифровка пароля
        except InvalidToken:  # Ошибка, возникающая при изменении ключа
            self.statusBar().showMessage('ВНИМАНИЕ! КЛЮЧ ШИФРОВАНИЯ БЫЛ ИЗМЕНЁН! '
                                         'ПАРОЛИ НЕ МОГУТЬ РАСШИФРОВАНЫ! '
                                         'ИЗМЕНИТЕ ВРУЧНУЮ ИЛИ УДАЛИТЕ ИХ.', 10000)
            self.statusBar().setStyleSheet('background-color:red;')  # изменение цвета статусбара
            QTimer.singleShot(5000, lambda: self.statusBar().setStyleSheet(''))  # возвращение цвета через 5 секунд
        except ValueError:
            message_box = QMessageBox()  # Создание мессаджбокса с уведомлением о ошибке

            # настройка message_box-а
            message_box.setWindowIcon(QIcon('logo/icon.ico'))
            message_box.setIcon(QMessageBox.Icon.Warning)
            message_box.setWindowTitle('Ошибка ключа')
            message_box.setText('Ключ шифрования вероятно был поврежден!\t\t')
            message_box.setInformativeText('Программа не может работать с повреждённым ключом, '
                                           'пожалуйста восстановите ключ или удалите его для генерации нового '
                                           '(вы потеряете все пароли при генерации нового ключа)')
            message_box.exec()
            sys.exit()  # закрытие приложения


class PasswordGeneratorDialog(QDialog):
    """Диалог для генератора паролей"""

    def __init__(self):
        super().__init__()
        uic.loadUi("UIs/PasswordGeneratorDialogUI.ui", self)  # Загрузка интерфейса
        self.initUI()

    def initUI(self):
        self.setWindowIcon(QIcon('logo/icon.ico'))
        self.dialog_buttons.accepted.connect(self.accept)  # Обработчик кнопки OK
        self.dialog_buttons.rejected.connect(self.reject)  # Обработчик кнопки Cancel

        self.load_settings()

    def load_settings(self):
        """Загрузка сохранённых настроек"""
        settings = QSettings('PasswordManagerApp', 'PasswordManager')

        # Загрузка состояния галочек и значение длины пароля
        self.include_special.setChecked(settings.value('include_special', False, type=bool))
        self.include_digits.setChecked(settings.value('include_digits', False, type=bool))
        self.include_uppercase.setChecked(settings.value('include_uppercase', False, type=bool))
        self.include_lowercase.setChecked(settings.value('include_lowercase', False, type=bool))
        self.password_length.setValue(settings.value('password_length', 8, type=int))

    def save_settings(self):
        """Сохранение настроек при закрытии окна"""
        settings = QSettings("PasswordManagerApp", "PasswordManager")

        # Сохраняем текущее состояние галочек и значение длины пароля
        settings.setValue('include_special', self.include_special.isChecked())
        settings.setValue('include_digits', self.include_digits.isChecked())
        settings.setValue('include_uppercase', self.include_uppercase.isChecked())
        settings.setValue('include_lowercase', self.include_lowercase.isChecked())
        settings.setValue('password_length', self.password_length.value())

    def accept(self):
        """Переопределение accept для сохранения настроек перед закрытием окна"""
        self.save_settings()  # Сохранение настроек перед закрытием
        super().accept()  # Вызов оригинального метода accept


class ConfirmDialog(QDialog):
    """Диалог для подтверждения действия"""

    def __init__(self):
        super().__init__()
        uic.loadUi("UIs/ConfirmDialogUI.ui", self)  # Загрузка интерфейса
        self.initUI()

    def initUI(self):
        self.setWindowIcon(QIcon('logo/icon.ico'))
        self.dialog_buttons.accepted.connect(self.accept)  # Обработчик кнопки OK
        self.dialog_buttons.rejected.connect(self.reject)  # Обработчик кнопки Cancel


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = PasswordManagerApp()
    window.show()
    sys.exit(app.exec())
