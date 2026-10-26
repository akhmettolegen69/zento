import io
import random

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from shop.models import Category, Product, Story, StorySlide

CATS = [('Women', '#B0305A'), ('Men', '#4C5BF5'), ('Kids', '#e07a1f'), ('Outerwear', '#2f5d62'),
        ('Sportswear', '#1f9d55'), ('Shoes', '#7b4b2a'), ('Accessories', '#6a4c93')]
# (product name, category slug)
ITEMS = [('Linen shirt', 'men'), ('Summer dress', 'women'), ('Kids hoodie', 'kids'), ('Puffer jacket', 'outerwear'),
         ('Running leggings', 'sportswear'), ('White sneakers', 'shoes'), ('Leather belt', 'accessories'),
         ('Wool scarf', 'accessories')]


def img(label, color, size=(800, 600)):
    im = Image.new('RGB', size, color)
    d = ImageDraw.Draw(im)
    d.ellipse((size[0] * .25, size[1] * .2, size[0] * .75, size[1] * .8), fill=(255, 255, 255))
    d.text((size[0] * .38, size[1] * .48), label, fill=color)
    buf = io.BytesIO()
    im.save(buf, 'JPEG')
    return ContentFile(buf.getvalue(), name=label.replace(' ', '_') + '.jpg')


class Command(BaseCommand):
    help = 'Create demo categories, products and stories with placeholder images'

    def handle(self, *args, **opts):
        random.seed(1)
        cats = []
        for i, (name, color) in enumerate(CATS):
            c, _ = Category.objects.get_or_create(name=name, slug=name.lower(), defaults={'color': color, 'position': i})
            if not c.image:
                c.image.save(f'{name}.jpg', img(name, color))
            cats.append((c, color))
        if not Product.objects.exists():
            by_slug = {c.slug: (c, color) for c, color in cats}
            for i, (name, slug) in enumerate(ITEMS):
                c, color = by_slug[slug]
                Product.objects.create(
                    name=name, category=c, image=img(name, color), price_kzt=random.randrange(3, 60) * 1000,
                    description=f'{name} — quality item shipped from our partner warehouse.',
                    available=i != 7, badge=['new', 'popular', '', 'sale'][i % 4],
                    delivery_days_min=5 + i, delivery_days_max=10 + i * 2)
        if not Story.objects.exists():
            for p in Product.objects.filter(available=True)[:5]:
                s = Story.objects.create(title=p.name[:14], cover=img(p.name, '#4C5BF5', (300, 300)), product=p)
                StorySlide.objects.create(story=s, image=img(p.name, '#222', (720, 1280)), caption=p.name)
                StorySlide.objects.create(story=s, image=img('Only ' + str(p.price_kzt) + ' KZT', '#B0305A', (720, 1280)), caption='Limited offer')
        self.stdout.write('Demo data created.')
