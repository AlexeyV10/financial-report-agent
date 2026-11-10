"""Evaluator only. Fraction/integer-cent reference with separate Decimal80 checks. No runtime imports."""
from datetime import datetime
from decimal import Decimal,localcontext,ROUND_HALF_UP
from fractions import Fraction as F


def cents(v):
    x=F(v)*100;s=-1 if x<0 else 1;n,d=abs(x.numerator),x.denominator;return s*((2*n+d)//(2*d))


def reference(dataset,request,signal,force_trade=False):
    p=request['parameters'];start,end,decision=[datetime.fromisoformat(v)for v in [p['window_start'],p['window_end'],request['decision_at']]];times=[datetime.fromisoformat(s[k])for s in dataset['calendar']['sessions']for k in ['open','close']if start<=datetime.fromisoformat(s[k])<=end];entry=min(datetime.fromisoformat(s['open'])for s in dataset['calendar']['sessions']if decision<datetime.fromisoformat(s['open'])<=end and start<=datetime.fromisoformat(s['open']));prices={datetime.fromisoformat(r['at']):F(r['price'])for r in dataset['prices']['observations']}
    capital=cents(p['initial_cash']);cash=capital;fee=cents(p['fee_fixed']);lot=p['lot_size'];slip=F(p['slippage_bps'])/10000;allocation=F(p['allocation']);q=0;entry_q=0;fees=0;slippage=0;peak=capital;dd=F(0);rows=[]
    for t in times:
        price=prices[t];action='mark';cost=0;paid=0;adverse=0
        if t==entry and(signal or force_trade):
            budget=max(0,min((capital*allocation).__floor__(),capital-fee));unit_price=price*(1+slip);q=(F(budget,100)/unit_price/lot).__floor__()*lot;entry_q=q;action='buy'if q else 'no_trade'
            if q:
                cost=cents(q*unit_price);paid=fee;cash-=cost+fee;fees+=fee;adverse=cost-cents(q*price);slippage+=adverse
                with localcontext()as ctx:
                    ctx.prec=80;decimal_price=Decimal(dataset['prices']['observations'][[datetime.fromisoformat(r['at'])for r in dataset['prices']['observations']].index(t)]['price']);value=Decimal(q)*decimal_price*(1+Decimal(p['slippage_bps'])/10000);assert Decimal(cost)/100==value.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        elif t==end and q:
            action='sell';cost=cents(q*price*(1-slip));paid=fee;cash+=cost-fee;fees+=fee;adverse=cents(q*price)-cost;slippage+=adverse;q=0
        equity=cash+cents(q*price);peak=max(peak,equity);dd=max(dd,F(peak-equity,peak));rows.append(dict(at=t.isoformat(),action=action,cash_cents=cash,quantity=q,equity_cents=equity,commission_cents=paid,gross_cents=cost,slippage_cents=adverse))
    with localcontext()as ctx:
        ctx.prec=80;dd_decimal=Decimal(dd.numerator)/Decimal(dd.denominator)*100;assert Decimal(cents(dd*100))/100==dd_decimal.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
    return dict(entry_at=entry.isoformat(),exit_at=end.isoformat(),entry_quantity=entry_q,rows=rows,final_cash_cents=cash,pnl_cents=cash-capital,fees_cents=fees,slippage_cents=slippage,return_percent_cents=cents(F(cash-capital,capital)*100),drawdown_ratio=dict(numerator=str(dd.numerator),denominator=str(dd.denominator)),drawdown_percent_cents=cents(dd*100))
