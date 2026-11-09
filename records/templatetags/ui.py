from django import forms, template

register = template.Library()


@register.filter
def bs(field):
    """Render a form field with the right Bootstrap class."""
    widget = field.field.widget
    if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect)):
        css = "form-check-input"
    elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
        css = "form-select"
    else:
        css = "form-control"
    classes = widget.attrs.get("class", "").split()
    if css not in classes:
        classes.append(css)
    if field.errors:
        classes.append("is-invalid")
    return field.as_widget(attrs={"class": " ".join(classes)})


@register.filter
def is_checkbox(field):
    return isinstance(field.field.widget, forms.CheckboxInput)


@register.filter
def get_item(mapping, key):
    return mapping.get(key)


@register.filter
def grade_color(grade):
    return {"A": "success", "B": "primary", "C": "info", "D": "warning", "E": "warning", "F": "danger"}.get(grade, "secondary")


@register.filter
def status_color(status):
    return {
        "ACTIVE": "success", "GRADUATED": "primary", "SUSPENDED": "warning", "WITHDRAWN": "secondary",
        "DRAFT": "secondary", "SUBMITTED": "warning", "APPROVED": "success",
        "CREATE": "success", "UPDATE": "primary", "DELETE": "danger", "LOGIN": "secondary", "APPROVE": "info",
    }.get(status, "secondary")
