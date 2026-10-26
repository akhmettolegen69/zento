from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Order, OrderItem, Product, SiteSettings, Story, StorySlide

admin.site.site_header = 'Zento admin'


def thumb(obj):
    f = getattr(obj, 'image', None) or getattr(obj, 'cover', None)
    return format_html('<img src="{}" style="height:48px;border-radius:8px">', f.url) if f else '—'


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'position')
    list_editable = ('position',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (thumb, 'name', 'category', 'price_kzt', 'price_cny_display', 'available',
                    'delivery_days_min', 'delivery_days_max', 'badge')
    list_editable = ('price_kzt', 'available', 'badge')
    list_filter = ('available', 'category')
    search_fields = ('name',)

    @admin.display(description='Price (CNY)')
    def price_cny_display(self, obj):
        return f'¥{obj.price_cny}'


class SlideInline(admin.TabularInline):
    model = StorySlide
    extra = 1


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = (thumb, 'title', 'product', 'active', 'expires_at', 'position')
    list_editable = ('active', 'position')
    inlines = [SlideInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'name', 'price_kzt', 'quantity')
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'status', 'total_kzt', 'total_cny', 'created_at')
    list_filter = ('status',)
    readonly_fields = ('total_kzt', 'total_cny', 'rate', 'payment_ref', 'created_at')
    inlines = [OrderItemInline]
