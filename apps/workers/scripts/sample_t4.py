from shared.db import get_session
from sqlalchemy import text
with get_session('prod') as s:
    r = s.execute(text('''
        SELECT nif, nombre, localidad, descripcion
        FROM companies
        WHERE tier='T4' AND ia_fit='fit'
        ORDER BY md5(nif)
        LIMIT 10;
    ''')).all()
    print('| # | NIF | Nombre | Localidad |')
    print('|---|-----|--------|-----------|')
    for i, row in enumerate(r, 1):
        print(f'| {i} | {row.nif} | {row.nombre} | {row.localidad} |')
