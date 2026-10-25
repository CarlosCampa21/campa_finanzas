"""Cálculos independientes de la interfaz. Importes en MXN."""
import calendar
from datetime import date, timedelta
import math
import sqlite3
import json

TYPES = ['Ingreso', 'Gasto', 'Transferencia', 'Pago de deuda', 'Reembolso']
CATEGORIES = ['Sueldo', 'Vivienda', 'Comida', 'Transporte', 'Servicios', 'Salud', 'Ocio', 'Otros']

def money(value, decimal='.'):
    text = str(value).strip().replace('$', '').replace(' ', '').replace('MXN', '')
    if not text or text.lower() == 'nan':
        raise ValueError('Importe vacío')
    negative = text.startswith('(') and text.endswith(')')
    text = text.strip('()')
    text = text.replace(',' if decimal == '.' else '.', '')
    if decimal == ',':
        text = text.replace(',', '.')
    result = float(text)
    if not math.isfinite(result):
        raise ValueError('Importe no finito')
    return round(-result if negative else result, 2)

def paydays(year, month, frequency, anchor):
    end = calendar.monthrange(year, month)[1]
    if frequency == 'Quincenal (15 y fin de mes)':
        return [date(year, month, 15), date(year, month, end)]
    if frequency == 'Mensual':
        return [date(year, month, min(anchor.day, end))]
    start = date(year, month, 1)
    step = 7 if frequency == 'Semanal' else 14
    delta = (start - anchor).days
    n = max(0, -(-delta // step))
    current = anchor + timedelta(days=n * step)
    result = []
    while current <= date(year, month, end):
        if current >= start:
            result.append(current)
        current += timedelta(days=step)
    return result

def debt_plan(debts, extra=0, strategy='Avalancha', months=360):
    rows = [dict(d) for d in debts if d['saldo'] > 0]
    balances = [float(d['saldo']) for d in rows]
    budget = sum(d['pago'] for d in rows) + extra
    history = []
    for month in range(1, months + 1):
        if sum(balances) < .005:
            break
        interest = [round(b * d['tasa'] / 1200, 2) for b, d in zip(balances, rows)]
        balances = [round(b + i, 2) for b, i in zip(balances, interest)]
        paid = 0
        for i, d in enumerate(rows):
            amount = min(balances[i], d['pago'])
            balances[i] = round(balances[i] - amount, 2)
            paid += amount
        available = max(0, budget - paid)
        order = sorted(range(len(rows)), key=lambda i: -rows[i]['tasa'] if strategy == 'Avalancha' else balances[i])
        for i in order:
            amount = min(balances[i], available)
            balances[i] = round(balances[i] - amount, 2)
            available -= amount
            paid += amount
        history.append({'Mes': month, 'Saldo': round(sum(balances), 2), 'Intereses': sum(interest), 'Pago': round(paid, 2)})
    return history

class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, value TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS movements (id INTEGER PRIMARY KEY, fecha TEXT, descripcion TEXT, monto REAL, tipo TEXT, categoria TEXT, cuenta TEXT)')
        if "import_key" not in [r[1] for r in self.db.execute("PRAGMA table_info(movements)")]:
            self.db.execute("ALTER TABLE movements ADD COLUMN import_key TEXT")
        self.db.commit()
    def settings(self):
        row = self.db.execute('SELECT value FROM settings WHERE id=1').fetchone()
        return json.loads(row[0]) if row else {}
    def save_settings(self, value):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES(1, ?)', (json.dumps(value),))
    def movements(self):
        keys = ['id', 'fecha', 'descripcion', 'monto', 'tipo', 'categoria', 'cuenta']
        return [dict(zip(keys, row)) for row in self.db.execute('SELECT id,fecha,descripcion,monto,tipo,categoria,cuenta FROM movements ORDER BY fecha, id')]
    def insert(self, rows, skip_duplicates=True):
        count = 0
        with self.db:
            for r in rows:
                values = (r['fecha'], r['descripcion'], r['monto'], r['tipo'], r['categoria'], r['cuenta'])
                import_key = r.get('_clave_importacion')
                exists = (self.db.execute('SELECT 1 FROM movements WHERE import_key=?', (import_key,)).fetchone() if import_key else self.db.execute('SELECT 1 FROM movements WHERE fecha=? AND descripcion=? AND monto=? AND tipo=? AND categoria=? AND cuenta=?', values).fetchone())
                if skip_duplicates and exists:
                    continue
                self.db.execute('INSERT INTO movements(fecha,descripcion,monto,tipo,categoria,cuenta,import_key) VALUES(?,?,?,?,?,?,?)', (*values,import_key))
                count += 1
        return count
    def delete(self, ids):
        with self.db:
            self.db.executemany('DELETE FROM movements WHERE id=?', [(int(i),) for i in ids])
