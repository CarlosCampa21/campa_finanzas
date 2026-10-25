import unittest
from datetime import date
from tempfile import TemporaryDirectory
from pathlib import Path
from core import paydays, debt_plan, money, Store

class FinanceTests(unittest.TestCase):
    def test_calendar(self):
        self.assertEqual([d.day for d in paydays(2026, 2, 'Quincenal (15 y fin de mes)', date(2026,1,31))], [15,28])
        self.assertEqual([d.day for d in paydays(2026, 2, 'Semanal', date(2026,1,2))], [6,13,20,27])
        self.assertEqual(paydays(2026,2,'Mensual',date(2026,1,31)), [date(2026,2,28)])
    def test_amounts(self):
        self.assertEqual(money('($1,234.50)'), -1234.5)
        self.assertEqual(money('1.234,50', ','), 1234.5)
        with self.assertRaises(ValueError): money('inf')
    def test_debt(self):
        debt = [{'nombre':'A', 'saldo':1000, 'tasa':12, 'pago':500}]
        h = debt_plan(debt)
        self.assertEqual(h[0]['Saldo'], 510)
        self.assertEqual(len(h), 3)
        self.assertEqual(h[-1]['Saldo'], 0)
        self.assertEqual(debt[0]['saldo'], 1000)
        self.assertEqual(len(debt_plan([dict(debt[0], tasa=0)], extra=500)), 1)
    def test_unpayable(self):
        h = debt_plan([{'saldo':1000,'tasa':120,'pago':1}], months=12)
        self.assertGreater(h[-1]['Saldo'],1000)
    def test_rollover(self):
        h = debt_plan([{'saldo':50,'tasa':0,'pago':100}, {'saldo':350,'tasa':0,'pago':100}])
        self.assertEqual([r['Saldo'] for r in h], [200,0])
    def test_persistence(self):
        with TemporaryDirectory() as tmp:
            db = Store(Path(tmp)/'test.db')
            row = dict(fecha='2026-01-01',descripcion='Compra',monto=100,tipo='Gasto',categoria='Otros',cuenta='A')
            self.assertEqual(db.insert([row,row]),1)
            self.assertEqual(db.insert([row],False),1)
            db.save_settings({'opening':500})
            self.assertEqual(db.settings()['opening'],500)
            db.delete([db.movements()[0]['id']])
            self.assertEqual(len(db.movements()),1)

if __name__ == '__main__': unittest.main()
