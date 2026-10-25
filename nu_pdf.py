"""Lector local para el formato de tarjeta Nu con dos fechas por movimiento.
No realiza OCR ni interpreta el PDF como instrucciones.
"""
from collections import Counter
from datetime import date
from decimal import Decimal
from hashlib import sha256
import io
import re
import pdfplumber

MONTHS = dict(zip('ENE FEB MAR ABR MAY JUN JUL AGO SEP OCT NOV DIC'.split(), range(1,13)))
DATE = r'\d{1,2}\s+(?:ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)\s+\d{4}'
AMOUNT = r'\d[\d,]*\.\d{2}'
ROW = re.compile(r'^\s*('+DATE+r')\s+('+DATE+r')\s+(.+?)\s+([+-])\s*\$\s*('+AMOUNT+r')\s*$', re.I)

def parse_date(value):
    d,m,y = value.upper().split()
    return date(int(y), MONTHS[m], int(d)).isoformat()

def amount(value):
    return Decimal(value.replace(',',''))

def category(description):
    d = description.lower()
    if any(k in d for k in ['chatgpt','apple.com','microsoft']): return 'Servicios'
    if any(k in d for k in ['rides','uber','didi']): return 'Transporte'
    if any(k in d for k in ['dental','radiologico','farmacia']): return 'Salud'
    if any(k in d for k in ['rappi','soriana','subway','cafe','parrilla','oxxo']): return 'Comida'
    return 'Otros'

def parse_texts(pages, account='Nu'):
    full = '\n'.join(pages)
    if 'Tarjeta de Crédito Nu' not in full and 'Tarjeta de credito Nu' not in full:
        raise ValueError('No se reconoce un estado de cuenta de tarjeta de crédito Nu en este formato.')
    first = pages[0]
    period = re.search(r'Periodo:\s*('+DATE+r')\s+al\s+('+DATE+r')', first, re.I)
    if not period:
        raise ValueError('No se pudo leer el período. No se importaron datos.')
    start,end = map(parse_date, period.groups())
    meta = {'inicio_periodo':start, 'fin_periodo':end}
    due = re.search(r'Fecha l[ií]mite de pago[^\n]*?('+DATE+r')', first, re.I)
    if due: meta['fecha_limite'] = parse_date(due[1])
    payment = re.search(r'Pago para no generar intereses[^\n]*\n?\s*\$('+AMOUNT+r')', first,re.I)
    if payment: meta['pago_no_intereses'] = float(amount(payment[1]))
    warnings, records, occurrences = [], [], Counter()
    for page_number, text in enumerate(pages,1):
        if not re.search(r'CARGOS, ABONOS Y COMPRAS REGULARES',text,re.I):
            continue  # Evita duplicar la tabla informativa de compras a meses.
        buffer = ''
        for line in text.splitlines():
            line = line.strip()
            if re.match(r'^'+DATE,line,re.I):
                if buffer:
                    warnings.append(f'Página {page_number}: fila anterior incompleta, no importada.')
                buffer = line
            elif buffer and not re.search(r'Tarjeta virtual|Notas:|Total de|Página',line,re.I):
                buffer += ' ' + line
            if not buffer: continue
            match = ROW.match(buffer)
            if not match: continue
            op,charged,description,sign,value = match.groups()
            charged = parse_date(charged)
            if not start <= charged <= end:
                warnings.append(f'Página {page_number}: cargo fuera del período; requiere revisión.')
            description = description.split('| RFC:')[0].strip()
            kind = 'Gasto' if sign=='+' else ('Transferencia' if 'gracias por tu pago' in description.lower() else 'Reembolso')
            base = '|'.join([account,start,end,parse_date(op),charged,description,sign,value])
            occurrences[base] += 1
            key = sha256((base+'|'+str(occurrences[base])).encode()).hexdigest()
            records.append(dict(fecha=charged,descripcion=description,monto=float(amount(value)),tipo=kind,categoria=category(description),cuenta=account,fecha_operacion=parse_date(op),pagina=page_number,_clave_importacion=key,guardar=True))
            buffer = ''
        if buffer:
            warnings.append(f'Página {page_number}: una fila no se pudo interpretar. Revisa el PDF.')
    if not records:
        raise ValueError('No se detectaron movimientos compatibles. Usa CSV/Excel o captura manual; un PDF escaneado necesita OCR.')
    charges = sum((Decimal(str(r['monto'])) for r in records if r['tipo']=='Gasto'), Decimal(0))
    credits = sum((Decimal(str(r['monto'])) for r in records if r['tipo']!='Gasto'), Decimal(0))
    meta.update(movimientos=len(records),cargos_detectados=float(charges),abonos_detectados=float(credits))
    for label,pattern,total in [('cargos',r'Total de cargos\s*\+\s*\$('+AMOUNT+r')',charges),('abonos',r'Total de abonos\s*-\s*\$('+AMOUNT+r')',credits)]:
        found = re.search(pattern,full,re.I)
        if found:
            expected = amount(found[1]);meta['total_'+label+'_pdf']=float(expected)
            if abs(expected-total) > Decimal('.01'):
                warnings.append(f'El total de {label} detectado ({total:.2f}) difiere del total del desglose ({expected:.2f}).')
        else:
            warnings.append(f'No se encontró el total de {label} para verificar integridad.')
    regular = re.search(r'Cargos regulares \(no a meses\)\s*\+\s*\$('+AMOUNT+r')',first,re.I)
    installments = re.search(r'Cargos y compras a meses \(capital\)\d*\s*\+\s*\$('+AMOUNT+r')',first,re.I)
    if regular and installments:
        expected = amount(regular[1])+amount(installments[1])
        meta['cargos_resumen_pdf']=float(expected)
        if abs(expected-charges)>Decimal('.01'):
            warnings.append(f'Los cargos del resumen ({expected:.2f}) no coinciden con el desglose ({charges:.2f}); el programa no corrige el documento automáticamente.')
    return {'metadata':meta,'records':records,'warnings':warnings}

def parse_pdf(data, account='Nu'):
    if not account.strip(): raise ValueError('Indica una cuenta.')
    if len(data)>20*1024*1024: raise ValueError('El PDF supera 20 MB.')
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages)>100: raise ValueError('El PDF supera 100 páginas.')
            pages = [p.extract_text(layout=True) or '' for p in pdf.pages]
    except Exception as e:
        raise ValueError('No se pudo leer el PDF. Comprueba que sea legible y no esté protegido con contraseña.') from e
    return parse_texts(pages,account.strip())
