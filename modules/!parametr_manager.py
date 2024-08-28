from modules.database_manager import SQLiteDB
# TODO написать нормальный менеджер параметров, если он вдруг понадобится. пока этот не работает)

class ParameterManager:
    def __init__(self, db):
        self.db = db
        self.parameters = {}

    def load_parameters(self):
        query = "SELECT name, value FROM parameters_table"
        parameters_from_db = self.db.select_from_table("parameters_table", columns="name, value")
        for row in parameters_from_db:
            self.parameters[row['name']] = row['value']

    def get_parameter(self, param_name):
        if param_name not in self.parameters:
            self.load_parameters()  # Если параметр не загружен, загружаем его
        return self.parameters.get(param_name)