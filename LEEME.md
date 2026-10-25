# Campa Finanzas · Python

Aplicación local para una persona, en pesos mexicanos. Python 3.10 o superior.

## Ejecutar en Mac

Descomprime el ZIP, abre Terminal y entra en la carpeta `campa_finanzas`:

```bash
cd /ruta/a/campa_finanzas
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1
```

## Ejecutar en Windows (PowerShell)

Abre PowerShell dentro de la carpeta descomprimida:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Abre http://localhost:8501 si no aparece automáticamente. Para cerrar: Ctrl+C en la terminal. Para volver a abrir, repite solo la activación y el último comando (Windows: solo el último comando).

## Primer recorrido

1. En Plan mensual configura el sueldo neto **por pago**, frecuencia y fecha. Semanal/cada 14 días empiezan a contar desde el primer cobro indicado. Quincenal son dos pagos, 15 y último día. Mensual usa el día de la fecha elegida.
2. En las tablas, agrega filas: fijos (`nombre`, `categoria`, `monto`, `dia`) y variables (`categoria`, `monto`). Usa días enteros 1–31. Los fijos y variables se suman: evita repetir la misma obligación en ambos.
3. Importa `ejemplo.csv` para probar. Selecciona fecha, descripción e importe, fecha `%Y-%m-%d`, decimal punto. Positivos son ingresos. Revisa y confirma. No se cargan datos de ejemplo automáticamente.
4. Registra tus deudas con saldo **actual**, tasa nominal anual y pago mensual. Una deuda se reserva en el plan cuando tiene saldo. No introduzcas de nuevo su pago base como gasto fijo.
5. Configura tu meta de ahorro y prueba un pago extra de deuda. El programa avisa si ambos superan el disponible mensual.
6. Revisa gráficos del Resumen y exporta el respaldo cuando quieras.

## Importar estados de cuenta

Admite CSV (coma, punto y coma o tabulador; UTF-8 o Latin-1) y XLSX con encabezados en la primera fila. Puedes mapear tus columnas y elegir signo o cargo/abono separados. Elige explícitamente formato de fecha y separador decimal. Cargos/abonos separados deben ser positivos, uno por fila. Las filas inválidas se reportan y quedan fuera de la revisión; corrígelas en el archivo de origen para volver a importarlas.

La revisión permite corregir categoría y tipo. Fechas deben quedar `AAAA-MM-DD`; importes, positivos. La omisión opcional de duplicados usa todos los campos de la fila, incluida la cuenta y categoría. Puede omitir compras legítimas idénticas: revísalo. No reconoce automáticamente la misma operación si cambias sus campos.

PDF, OCR, sincronización bancaria y detección automática de categorías **no están incluidos**. Si tu banco solo entrega PDF, hace falta adaptar un lector a una muestra de ese banco. Nunca renombres un PDF como CSV.

## Interpretación y límites

- El plan es una plantilla recurrente que se aplica a cualquier mes seleccionado; editarla modifica la proyección de todos los meses, no guarda versiones históricas.
- Ingresos estimados y reales se muestran por separado. El disponible es ingreso **estimado** menos fijos, presupuestos variables y pagos base; no es dinero bancario disponible.
- El calendario usa un saldo inicial común configurable. Variables y pagos de deuda se descuentan al final de mes; para pagos reales consulta Movimientos. No es un calendario bancario preciso de vencimientos.
- Las comparaciones suman fijos y variables por categoría frente a gastos reales del mes. Los pagos de deuda se muestran por separado.
- Compra con tarjeta: Gasto; su pago posterior: Transferencia, para no contar dos veces. Una deuda anterior al período de registro puede clasificarse como Pago de deuda. Las transferencias entre cuentas propias no son ingresos/gastos. Revisa ambas caras si importas varias cuentas.
- Deudas: tasa nominal anual / 12 aplicada mensualmente al saldo, luego pagos; presupuesto total constante, cuotas liberadas se reasignan. No incluye IVA, CAT, comisiones, seguros, intereses diarios ni compras nuevas. Máximo 360 meses. Los saldos se actualizan manualmente: un movimiento importado no los modifica.
- Ahorro: plazo por aportación constante sin rendimiento. La gráfica limita la visualización a 120 meses.
- Una moneda (MXN), un usuario local. No hay inicio de sesión, cifrado de base ni protección multiusuario. No publiques esta versión con datos personales en Internet.

## Datos y respaldo

Se guardan en `datos/finanzas.sqlite3` junto a la aplicación. No se envían a un banco ni a una IA. Exporta la base desde Respaldo. Para restaurar, cierra la aplicación, conserva una copia de la base anterior y reemplaza el archivo por tu respaldo. Los CSV exportan movimientos, pero no contienen la configuración ni las metas. No borres la carpeta `datos` al actualizar.

## Estructura y pruebas

- `app.py`: interfaz Streamlit.
- `core.py`: calendario, importes, simulación y SQLite.
- `test_core.py`: pruebas del cálculo y persistencia.
- `ejemplo.csv`: datos ficticios, sin información personal.

```bash
python -m unittest -v
```
