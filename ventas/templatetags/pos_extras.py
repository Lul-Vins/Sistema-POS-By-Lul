from django import template

register = template.Library()


@register.filter
def formato_bs(value):
    """Formato venezolano: punto para miles, coma para decimal. Ej: 1.000,00"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    # f"{:,.2f}" usa coma para miles y punto para decimal (inglés)
    # lo invertimos al formato venezolano
    formatted = f"{num:,.2f}"
    return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')


@register.filter
def formato_cantidad(cantidad, por_peso):
    """
    Formatea la cantidad de un detalle de venta con su unidad.
    Por peso: < 1 kg → gramos ("300 gr"), >= 1 kg → kilos con coma ("1,5 kg").
    Por unidad: entero sin unidad ("2").
    """
    val = float(cantidad)
    if por_peso:
        if val < 1:
            gramos = int(round(val * 1000))
            return f"{gramos} gr"
        else:
            return f"{val:.3f}".rstrip('0').rstrip('.').replace('.', ',') + " kg"
    else:
        return str(int(round(val)))
