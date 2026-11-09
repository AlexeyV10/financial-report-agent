"""Evaluator-only Fraction reference. No production imports, paths, retrieval or gold at runtime."""
from decimal import Decimal,localcontext,ROUND_HALF_UP
from fractions import Fraction


def evaluate(operation,values,source_scale,target_scale):
    a=[Fraction(v) for v in values]
    if operation=='direct_fact_v1':v=a[0]
    elif operation=='absolute_change_v1':v=a[1]-a[0]
    elif operation=='relative_change_v1':
        if a[0]<=0:return dict(status='unsupported',reason='nonpositive_base')
        v=(a[1]/a[0]-1)*100
    elif operation=='scale_v1':v=a[0]*Fraction(source_scale,target_scale)
    elif operation=='operating_margin_v1':
        if a[1]==0:return dict(status='unsupported',reason='zero_denominator')
        if a[1]<0:return dict(status='unsupported',reason='negative_revenue_denominator')
        v=a[0]*100/a[1]
    else:raise ValueError('reference operation outside P0')
    percent=operation in {'relative_change_v1','operating_margin_v1'}
    if percent:
        # Exact rational HALF_UP, with Decimal80 as a separately computed check.
        magnitude=abs(v)*100;whole=magnitude.numerator//magnitude.denominator
        rounded=whole+(magnitude-whole>=Fraction(1,2))
        display=('-' if v<0 and rounded else '')+str(rounded//100)+'.'+str(rounded%100).zfill(2)
    else:
        with localcontext() as c:
            c.prec=200
            s=format(Decimal(v.numerator)/Decimal(v.denominator),'f')
        display=values[0] if operation=='direct_fact_v1' else (s.rstrip('0').rstrip('.') if '.' in s else s)
    with localcontext() as c:
        c.prec=80
        b=[Decimal(x)for x in values]
        if operation=='direct_fact_v1':d=b[0]
        elif operation=='absolute_change_v1':d=b[1]-b[0]
        elif operation=='relative_change_v1':d=(b[1]-b[0])/b[0]*100
        elif operation=='scale_v1':d=b[0]*Decimal(source_scale)/Decimal(target_scale)
        else:d=b[0]/b[1]*100
        if percent:
            d=d.quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
            if d==0:d=abs(d)
        assert Decimal(display)==d,'independent Decimal80 mismatch'
    return dict(status='answered',reason='ok',exact_result=dict(numerator=str(v.numerator),denominator=str(v.denominator)),display_value=display)
