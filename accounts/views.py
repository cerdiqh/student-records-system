from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .decorators import admin_required
from .forms import StaffUserForm
from .models import User


@admin_required
def staff_list(request):
    users = User.objects.exclude(role=User.Role.STUDENT)
    q = request.GET.get("q", "").strip()
    if q:
        users = users.filter(
            Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(email__icontains=q)
        )
    role = request.GET.get("role")
    if role:
        users = users.filter(role=role)
    page = Paginator(users, 20).get_page(request.GET.get("page"))
    return render(request, "accounts/staff_list.html", {"page": page, "q": q, "roles": User.Role.choices, "role": role})


@admin_required
def staff_form(request, pk=None):
    user = get_object_or_404(User, pk=pk) if pk else None
    if user and user.is_student:
        return redirect("student_edit", pk=user.student_profile.pk)
    form = StaffUserForm(request.POST or None, instance=user)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Account for {saved} saved.")
        return redirect("staff_list")
    return render(request, "form.html", {"form": form, "title": "Edit staff account" if user else "New staff account", "back": "staff_list"})
