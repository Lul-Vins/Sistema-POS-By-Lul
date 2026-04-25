"""
Comando: python manage.py seed_productos
Inserta ~3000 productos de abasto realistas en la base de datos para pruebas de carga.
Idempotente: si ya existen productos con el mismo nombre los omite.
"""

import random
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction


CATEGORIAS_PRODUCTOS = {
    'Granos y Cereales': [
        ('Arroz Diana 1kg', 1.20, 1.50),
        ('Arroz Mary 1kg', 1.10, 1.40),
        ('Arroz Primor 2kg', 2.20, 2.80),
        ('Caraotas Negras 500g', 0.90, 1.20),
        ('Caraotas Rojas 500g', 0.85, 1.15),
        ('Lentejas 500g', 0.80, 1.10),
        ('Frijoles Negros 1kg', 1.50, 2.00),
        ('Quinoa 400g', 2.50, 3.20),
        ('Avena en Hojuelas 500g', 0.75, 1.00),
        ('Avena Instantanea 400g', 0.80, 1.05),
        ('Maiz Pilado 1kg', 1.00, 1.30),
        ('Cebada Perlada 500g', 0.70, 0.95),
        ('Trigo Entero 1kg', 1.10, 1.45),
        ('Harina Pan 1kg', 1.30, 1.65),
        ('Harina Juana 1kg', 1.25, 1.60),
        ('Harina Integral 1kg', 1.40, 1.80),
        ('Harina de Maiz Amarilla 1kg', 1.20, 1.55),
        ('Semola de Trigo 500g', 0.85, 1.10),
        ('Garbanzo 500g', 1.00, 1.35),
        ('Arvejas Verdes 500g', 0.90, 1.20),
    ],
    'Aceites y Grasas': [
        ('Aceite Vatel 1L', 2.50, 3.20),
        ('Aceite Mazeite 1L', 2.40, 3.10),
        ('Aceite Italcambio 900ml', 2.20, 2.90),
        ('Aceite de Girasol 1L', 2.60, 3.30),
        ('Aceite de Oliva Extra Virgen 500ml', 5.50, 7.00),
        ('Aceite Bello 1L', 2.35, 3.00),
        ('Aceite Omega 3 1L', 3.00, 3.80),
        ('Mantequilla Planta 200g', 1.20, 1.60),
        ('Mantequilla Mavesa 200g', 1.30, 1.70),
        ('Margarina Natalio 250g', 1.10, 1.45),
        ('Margarina Regia 500g', 1.80, 2.30),
        ('Aceite de Coco 400ml', 4.00, 5.20),
        ('Aceite de Maiz 1L', 2.45, 3.15),
        ('Aceite de Soya 1L', 2.30, 2.95),
        ('Shortening Palmar 500g', 1.50, 1.95),
    ],
    'Lacteos y Huevos': [
        ('Leche Completa Parmalat 1L', 1.80, 2.30),
        ('Leche Descremada Parmalat 1L', 1.90, 2.40),
        ('Leche en Polvo Nestle 400g', 4.50, 5.80),
        ('Leche en Polvo Completa 900g', 9.00, 11.50),
        ('Leche Condensada Nestle 395g', 2.20, 2.80),
        ('Leche Evaporada Carnation 410g', 1.80, 2.35),
        ('Yogur Natural 1kg', 2.00, 2.60),
        ('Yogur de Fresa 250g', 0.80, 1.05),
        ('Yogur de Durazno 250g', 0.80, 1.05),
        ('Queso Amarillo Lonchas 150g', 2.50, 3.20),
        ('Queso Blanco Pasteurizado 500g', 3.00, 3.90),
        ('Queso Mozarella 250g', 2.80, 3.60),
        ('Queso Crema 250g', 1.80, 2.30),
        ('Mantequilla con Sal 200g', 1.50, 1.95),
        ('Crema de Leche 200ml', 1.20, 1.55),
        ('Huevos Blancos Carton x30', 4.50, 5.80),
        ('Huevos Marrones Carton x12', 2.00, 2.60),
        ('Huevos Carton x6', 1.10, 1.45),
        ('Kumis 200ml', 0.60, 0.80),
        ('Buttermilk 500ml', 1.20, 1.55),
    ],
    'Carnes y Embutidos': [
        ('Jamonada de Pollo 250g', 1.50, 1.95),
        ('Mortadela con Aceitunas 250g', 1.60, 2.10),
        ('Salchicha de Res Viena 250g', 2.00, 2.60),
        ('Salchicha de Pollo 500g', 3.20, 4.10),
        ('Jamon Cocido 200g', 2.50, 3.20),
        ('Pernil Ahumado 300g', 3.00, 3.85),
        ('Chorizo Espanol 200g', 2.80, 3.60),
        ('Bacon Ahumado 150g', 2.20, 2.85),
        ('Pepperoni 100g', 1.50, 1.95),
        ('Salami 150g', 2.00, 2.60),
        ('Atun en Agua Caju 170g', 1.20, 1.55),
        ('Atun en Aceite Caju 170g', 1.30, 1.70),
        ('Sardinas en Salsa de Tomate 425g', 1.40, 1.80),
        ('Sardinas en Aceite 150g', 1.00, 1.30),
        ('Salmon Enlatado 180g', 2.50, 3.20),
        ('Pollo Entero Congelado 1.5kg', 5.00, 6.50),
        ('Pechuga de Pollo 1kg', 4.00, 5.20),
        ('Carne Molida 500g', 3.50, 4.55),
        ('Costilla de Res 1kg', 5.50, 7.15),
        ('Chuleta de Cerdo 500g', 3.80, 4.95),
    ],
    'Pastas y Fideos': [
        ('Pasta Capellini Valerio 500g', 0.70, 0.95),
        ('Spaghetti Catanella 500g', 0.65, 0.88),
        ('Macarron Corto Pampero 500g', 0.68, 0.90),
        ('Tallarines Ronco 500g', 0.70, 0.93),
        ('Plumas Rayadas Primor 500g', 0.72, 0.96),
        ('Conchitas Medianas 500g', 0.75, 1.00),
        ('Cabellos de Angel 500g', 0.65, 0.87),
        ('Lasagna Valerio 500g', 1.00, 1.35),
        ('Fetuccini 500g', 0.80, 1.05),
        ('Rigatoni 500g', 0.78, 1.03),
        ('Pasta Integral 500g', 1.20, 1.55),
        ('Fideos Finos 500g', 0.60, 0.80),
        ('Pasta para Sopa 250g', 0.40, 0.55),
        ('Pasta de Trigo Sarraceno 500g', 1.50, 1.95),
        ('Vermicelli 500g', 0.65, 0.87),
    ],
    'Condimentos y Salsas': [
        ('Sal Refinada Salsalito 1kg', 0.40, 0.55),
        ('Sal de Mesa 500g', 0.30, 0.42),
        ('Azucar Blanca Diana 1kg', 0.90, 1.20),
        ('Azucar Morena 500g', 0.80, 1.05),
        ('Papelón Rallado 500g', 1.20, 1.55),
        ('Pimienta Negra Molida 50g', 0.60, 0.80),
        ('Comino Molido 50g', 0.55, 0.75),
        ('Oregano Seco 20g', 0.40, 0.55),
        ('Ajo en Polvo 50g', 0.65, 0.87),
        ('Cebolla en Polvo 50g', 0.60, 0.80),
        ('Pimenton Dulce 50g', 0.70, 0.93),
        ('Curry en Polvo 50g', 0.80, 1.05),
        ('Canela Molida 30g', 0.55, 0.73),
        ('Clavos de Olor 20g', 0.50, 0.68),
        ('Pimienta de Guayabita 20g', 0.60, 0.80),
        ('Salsa de Tomate Ketchup Heinz 397g', 1.80, 2.30),
        ('Mostaza Americana 295g', 1.20, 1.55),
        ('Mayonesa McCormick 400g', 2.00, 2.60),
        ('Salsa Inglesa Lea & Perrins 150ml', 1.50, 1.95),
        ('Salsa de Soya Kikoman 150ml', 1.40, 1.80),
        ('Vinagre Blanco 500ml', 0.60, 0.80),
        ('Vinagre de Manzana 500ml', 1.20, 1.55),
        ('Salsa Picante Tabasco 60ml', 1.80, 2.35),
        ('Salsa BBQ 350g', 1.60, 2.10),
        ('Salsa de Ajo 250g', 1.00, 1.30),
        ('Caldo de Pollo Maggi x8', 0.80, 1.05),
        ('Caldo de Res Maggi x8', 0.80, 1.05),
        ('Sazonador Completo Maggi 100g', 0.90, 1.20),
        ('Onoto Molido 50g', 0.45, 0.62),
        ('Paprika Ahumada 50g', 0.75, 1.00),
    ],
    'Enlatados y Conservas': [
        ('Tomates Triturados Panzani 400g', 1.00, 1.30),
        ('Tomates Enteros Pelados 400g', 1.10, 1.45),
        ('Pasta de Tomate Heinz 170g', 0.80, 1.05),
        ('Pure de Tomate 400g', 0.90, 1.20),
        ('Maiz en Lata Bonduelle 280g', 1.20, 1.55),
        ('Guisantes en Lata 400g', 1.10, 1.45),
        ('Palmitos en Lata 400g', 2.00, 2.60),
        ('Aceitunas Negras 200g', 1.50, 1.95),
        ('Aceitunas Verdes Rellenas 200g', 1.60, 2.10),
        ('Champinones en Lata 200g', 1.40, 1.80),
        ('Pimientos en Lata 340g', 1.30, 1.70),
        ('Alcachofas en Aceite 280g', 2.50, 3.25),
        ('Melocotones en Almibar 825g', 2.00, 2.60),
        ('Peras en Almibar 820g', 1.90, 2.45),
        ('Duraznos en Almibar 400g', 1.50, 1.95),
        ('Frijoles Bayos Refritos 430g', 1.20, 1.55),
        ('Chili con Carne 425g', 2.00, 2.60),
        ('Sopa de Pollo Campbell 305g', 1.50, 1.95),
        ('Sopa de Tomate Campbell 305g', 1.40, 1.80),
        ('Creme de Mushroom 305g', 1.50, 1.95),
    ],
    'Bebidas': [
        ('Agua Mineral Minalba 500ml', 0.50, 0.68),
        ('Agua Mineral Minalba 1.5L', 0.90, 1.20),
        ('Agua con Gas San Benedetto 750ml', 1.20, 1.55),
        ('Gatorade Naranja 600ml', 1.50, 1.95),
        ('Gatorade Limón 600ml', 1.50, 1.95),
        ('Powerade Frutos Rojos 500ml', 1.40, 1.80),
        ('Jugo de Naranja Hit 400ml', 0.90, 1.20),
        ('Jugo de Mango Hit 400ml', 0.90, 1.20),
        ('Jugo de Guayaba 1L', 1.50, 1.95),
        ('Néctar de Pera 1L', 1.60, 2.10),
        ('Leche de Almendras 1L', 2.50, 3.25),
        ('Refresco Cola 2L', 1.80, 2.35),
        ('Refresco de Naranja 2L', 1.70, 2.20),
        ('Refresco de Uva 2L', 1.70, 2.20),
        ('Té Frío Nestea Limón 500ml', 0.90, 1.20),
        ('Té Frío Nestea Melocotón 500ml', 0.90, 1.20),
        ('Café Molido Fama de América 250g', 2.00, 2.60),
        ('Café Soluble Nescafé Clásico 170g', 4.50, 5.85),
        ('Café en Grano El Pedregal 500g', 5.00, 6.50),
        ('Té Verde Twinings x25', 2.50, 3.25),
        ('Té Negro Hornimans x25', 1.80, 2.35),
        ('Manzanilla Hornimans x25', 1.50, 1.95),
        ('Cacao en Polvo Toddy 400g', 2.00, 2.60),
        ('Chocolate Caliente Ricacao 200g', 1.80, 2.35),
        ('Malteada Nesquik Fresa 400g', 2.20, 2.85),
    ],
    'Panaderia y Reposteria': [
        ('Harina Leudante Blancaflor 1kg', 1.30, 1.70),
        ('Harina Todo Uso 1kg', 1.20, 1.55),
        ('Levadura Seca Fleischmann 10g', 0.50, 0.68),
        ('Polvo de Hornear 100g', 0.60, 0.80),
        ('Bicarbonato de Sodio 200g', 0.40, 0.55),
        ('Chocolate en Barra Nestlé 200g', 2.00, 2.60),
        ('Cacao Amargo Caraibos 250g', 2.50, 3.25),
        ('Vainilla Liquida 60ml', 0.80, 1.05),
        ('Esencia de Almendra 30ml', 0.70, 0.93),
        ('Gelatina de Fresa Royal 90g', 0.60, 0.80),
        ('Gelatina de Naranja Royal 90g', 0.60, 0.80),
        ('Gelatina sin Sabor Knox 7g', 0.50, 0.68),
        ('Maizina Americana 200g', 0.70, 0.93),
        ('Crema Pastelera Polvo 100g', 0.90, 1.20),
        ('Azucar Glass 250g', 0.70, 0.93),
        ('Azucar Impalpable 500g', 1.20, 1.55),
        ('Miel de Abeja Natural 500g', 4.00, 5.20),
        ('Mermelada de Fresa Smucker 340g', 1.80, 2.35),
        ('Mermelada de Mango 340g', 1.70, 2.20),
        ('Mermelada de Guayaba 340g', 1.60, 2.10),
        ('Mantequilla de Mani 340g', 2.00, 2.60),
        ('Nutella 200g', 3.00, 3.90),
        ('Arroz con Leche Instantaneo 200g', 1.00, 1.30),
        ('Flan de Caramelo Royal 90g', 0.80, 1.05),
        ('Budín de Vainilla 200g', 1.20, 1.55),
    ],
    'Snacks y Galletas': [
        ('Galletas Oreo Original 144g', 1.50, 1.95),
        ('Galletas Oreo Doble 144g', 1.60, 2.10),
        ('Galletas Chips Ahoy 200g', 2.00, 2.60),
        ('Galletas Ritz 200g', 1.80, 2.35),
        ('Galletas Maria 200g', 0.90, 1.20),
        ('Galletas de Avena 150g', 1.00, 1.30),
        ('Galletas Soda 300g', 0.80, 1.05),
        ('Galletas de Coco 150g', 1.00, 1.30),
        ('Papas Fritas Pringles Original 165g', 2.50, 3.25),
        ('Papas Fritas Lays Limon 45g', 0.70, 0.93),
        ('Papas Fritas Cheetos 45g', 0.60, 0.80),
        ('Maiz Tostado Salado 100g', 0.50, 0.68),
        ('Palomitas de Maiz Microondas 100g', 0.80, 1.05),
        ('Cacahuates Tostados 100g', 0.70, 0.93),
        ('Semillas de Girasol 100g', 0.65, 0.87),
        ('Mezcla de Frutos Secos 200g', 2.50, 3.25),
        ('Barra de Granola 30g', 0.60, 0.80),
        ('Barra de Chocolate KitKat 41.5g', 0.90, 1.20),
        ('Chocolate Snickers 52g', 0.80, 1.05),
        ('Caramelos Halls x12', 0.50, 0.68),
    ],
    'Higiene Personal': [
        ('Shampoo Pantene Clasico 400ml', 3.50, 4.55),
        ('Shampoo Head & Shoulders 400ml', 4.00, 5.20),
        ('Acondicionador Pantene 400ml', 3.50, 4.55),
        ('Jabon de Baño Dove 135g', 1.20, 1.55),
        ('Jabon de Baño Lux 135g', 1.00, 1.30),
        ('Jabon Antibacterial Protex 135g', 1.30, 1.70),
        ('Gel de Ducha Nivea Men 250ml', 2.50, 3.25),
        ('Desodorante Axe Body Spray 150ml', 3.00, 3.90),
        ('Desodorante Speed Stick 60g', 2.00, 2.60),
        ('Pasta Dental Colgate Triple Accion 75ml', 1.50, 1.95),
        ('Pasta Dental Sensodyne 75ml', 2.50, 3.25),
        ('Cepillo Dental Colgate 360', 1.50, 1.95),
        ('Cepillo Dental Oral-B Suave', 1.80, 2.35),
        ('Hilo Dental Oral-B 50m', 1.20, 1.55),
        ('Enjuague Bucal Listerine 250ml', 2.50, 3.25),
        ('Crema Hidratante Nivea 250ml', 2.00, 2.60),
        ('Crema Corporal Palmolive 200ml', 1.80, 2.35),
        ('Afeitadora Gillete Azul x3', 2.00, 2.60),
        ('Gel de Afeitar Gillete 200ml', 2.50, 3.25),
        ('Talco Johnson Baby 200g', 1.80, 2.35),
    ],
    'Limpieza del Hogar': [
        ('Detergente en Polvo Ace 1kg', 3.00, 3.90),
        ('Detergente en Polvo Ariel 1kg', 3.50, 4.55),
        ('Detergente Liquido Ariel 900ml', 4.00, 5.20),
        ('Suavizante de Ropa Downy 900ml', 3.00, 3.90),
        ('Blanqueador Clorox 1L', 1.50, 1.95),
        ('Desinfectante Pino Sol 1L', 2.00, 2.60),
        ('Limpiador Multiuso Fabuloso 1L', 1.80, 2.35),
        ('Limpiavidrios Windex 500ml', 2.00, 2.60),
        ('Esponja Scotch-Brite x2', 0.80, 1.05),
        ('Jabón Lavar Vajilla Axion 500g', 1.20, 1.55),
        ('Jabón Lavar Vajilla Joy 500ml', 1.50, 1.95),
        ('Servilletas Papel x100', 0.80, 1.05),
        ('Papel Toalla Scott x2', 1.50, 1.95),
        ('Papel Higienico Scott x4', 2.00, 2.60),
        ('Papel Higienico Suave x12', 5.00, 6.50),
        ('Bolsas de Basura 30L x10', 0.80, 1.05),
        ('Bolsas de Basura 70L x5', 0.90, 1.20),
        ('Guantes de Caucho Talla M', 1.00, 1.30),
        ('Escoba con Recogedor', 2.50, 3.25),
        ('Trapeador Microfibra', 3.00, 3.90),
    ],
    'Frutas y Verduras': [
        ('Tomate Rojo kg', 1.00, 1.35),
        ('Cebolla Cabezona kg', 0.90, 1.20),
        ('Pimiento Rojo kg', 1.50, 1.95),
        ('Pimiento Verde kg', 1.20, 1.55),
        ('Zanahoria kg', 0.80, 1.05),
        ('Papa Blanca kg', 0.70, 0.95),
        ('Ajo Cabeza', 0.50, 0.68),
        ('Lechuga Romana unidad', 0.80, 1.05),
        ('Repollo Blanco unidad', 1.00, 1.30),
        ('Berenjena kg', 1.20, 1.55),
        ('Calabacin kg', 1.00, 1.30),
        ('Auyama kg', 0.60, 0.80),
        ('Platano Verde kg', 0.70, 0.93),
        ('Platano Maduro kg', 0.80, 1.05),
        ('Cambur unidad', 0.20, 0.28),
        ('Naranja unidad', 0.30, 0.42),
        ('Mandarina unidad', 0.25, 0.35),
        ('Melon unidad', 2.50, 3.25),
        ('Parchita unidad', 0.50, 0.68),
        ('Guayaba kg', 1.00, 1.30),
        ('Mango kg', 0.80, 1.05),
        ('Papaya kg', 0.90, 1.20),
        ('Fresa 500g', 2.00, 2.60),
        ('Uvas Rojas 500g', 2.50, 3.25),
        ('Kiwi unidad', 0.80, 1.05),
    ],
    'Congelados': [
        ('Pizza Margherita Congelada 450g', 5.00, 6.50),
        ('Pizza de Jamon y Queso 450g', 5.50, 7.15),
        ('Nuggets de Pollo 500g', 4.00, 5.20),
        ('Hamburguesas Congeladas x4', 5.00, 6.50),
        ('Papas Fritas Congeladas McCain 750g', 3.50, 4.55),
        ('Mezcla de Vegetales Congelados 500g', 2.00, 2.60),
        ('Brocoli Congelado 500g', 2.20, 2.85),
        ('Espinaca Congelada 500g', 2.00, 2.60),
        ('Camarones Congelados 500g', 7.00, 9.10),
        ('Filetes de Tilapia 500g', 4.50, 5.85),
        ('Helado de Vainilla 1L', 4.00, 5.20),
        ('Helado de Chocolate 1L', 4.00, 5.20),
        ('Helado de Fresa 1L', 4.00, 5.20),
        ('Paletas de Fruta x6', 2.50, 3.25),
        ('Empanadas de Pollo Congeladas x5', 3.50, 4.55),
    ],
    'Bebe y Maternidad': [
        ('Panales Pampers Talla 1 x20', 8.00, 10.40),
        ('Panales Pampers Talla 2 x18', 8.50, 11.05),
        ('Panales Pampers Talla 3 x16', 9.00, 11.70),
        ('Panales Huggies Talla 2 x18', 8.00, 10.40),
        ('Toallitas Humedas Pampers x72', 3.50, 4.55),
        ('Formula Nestlé NAN 1 400g', 15.00, 19.50),
        ('Formula Enfamil 1 400g', 14.00, 18.20),
        ('Cereal Gerber Arroz 227g', 4.50, 5.85),
        ('Puré de Manzana Gerber 113g', 1.50, 1.95),
        ('Jugo de Manzana Gerber 125ml', 1.20, 1.55),
        ('Crema Cambrel 100g', 2.00, 2.60),
        ('Talco Johnson Baby 100g', 1.50, 1.95),
        ('Shampoo Johnson Baby 400ml', 3.00, 3.90),
        ('Colonia Nenuco 200ml', 2.50, 3.25),
        ('Biberón Avent 260ml', 4.00, 5.20),
    ],
    'Mascotas': [
        ('Alimento Perro Pedigree Adult 1kg', 3.50, 4.55),
        ('Alimento Perro Pedigree Cachorro 1kg', 4.00, 5.20),
        ('Alimento Gato Whiskas Adult 500g', 2.50, 3.25),
        ('Alimento Gato Felix Salmon 400g', 2.80, 3.65),
        ('Snack Perro Milkbone 250g', 2.00, 2.60),
        ('Snack Gato Dreamies 60g', 1.20, 1.55),
        ('Arena para Gatos 4kg', 4.00, 5.20),
        ('Shampoo para Perros 250ml', 2.50, 3.25),
        ('Antipulgas Frontline Collar', 8.00, 10.40),
        ('Juguete Peluche para Perro', 2.00, 2.60),
    ],
}


class Command(BaseCommand):
    help = 'Inserta ~3000 productos de abasto en la base de datos para prueba de carga'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limpiar', action='store_true',
            help='Elimina primero todos los productos y categorias existentes'
        )

    def handle(self, *args, **options):
        from inventario.models import Producto, Categoria

        if options['limpiar']:
            self.stdout.write('Eliminando productos y categorias existentes...')
            Producto.objects.all().delete()
            Categoria.objects.all().delete()

        creados_cat = 0
        creados_prod = 0
        omitidos = 0

        nombres_existentes = set(Producto.objects.values_list('nombre', flat=True))

        self.stdout.write(f'Iniciando carga masiva de productos...')

        with transaction.atomic():
            # Obtener o crear todas las categorias
            categorias = {}
            for nombre_cat in CATEGORIAS_PRODUCTOS:
                cat, fue_creada = Categoria.objects.get_or_create(nombre=nombre_cat)
                categorias[nombre_cat] = cat
                if fue_creada:
                    creados_cat += 1

            # Construir lista de todos los productos base
            productos_base = []
            for nombre_cat, items in CATEGORIAS_PRODUCTOS.items():
                cat = categorias[nombre_cat]
                for nombre, costo_min, precio_max in items:
                    productos_base.append((nombre_cat, cat, nombre, costo_min, precio_max))

            # Repetir/variar productos hasta llegar a ~3000
            objetivo = 3000
            lote = []

            multiplicador = 1
            while len(lote) + creados_prod < objetivo:
                for nombre_cat, cat, nombre_base, costo_min, precio_max in productos_base:
                    if len(lote) + creados_prod >= objetivo:
                        break

                    # Variantes: presentaciones, marcas alternativas
                    if multiplicador == 1:
                        nombre_final = nombre_base
                    else:
                        variantes_sufijo = [
                            'Economico', 'Premium', 'Familiar', 'Personal',
                            'Especial', 'Oferta', 'Importado', 'Nacional',
                            'Light', 'Extra',
                        ]
                        sufijo = variantes_sufijo[(multiplicador - 2) % len(variantes_sufijo)]
                        nombre_final = f'{nombre_base} ({sufijo})'

                    if nombre_final in nombres_existentes:
                        omitidos += 1
                        continue

                    # Precio con leve variacion
                    factor = random.uniform(0.92, 1.08)
                    precio_usd = round(precio_max * factor, 4)
                    costo_usd  = round(costo_min * factor * random.uniform(0.85, 0.95), 4)
                    stock      = random.randint(0, 150)
                    alicuota   = random.choices(
                        ['GENERAL', 'REDUCIDA', 'EXENTO'],
                        weights=[70, 15, 15]
                    )[0]

                    lote.append(Producto(
                        nombre        = nombre_final,
                        categoria     = cat,
                        precio_usd    = Decimal(str(precio_usd)),
                        costo_usd     = Decimal(str(costo_usd)),
                        stock_actual  = stock,
                        stock_minimo  = random.randint(2, 10),
                        activo        = True,
                        alicuota_iva  = alicuota,
                    ))
                    nombres_existentes.add(nombre_final)

                    # Insertar en lotes de 500
                    if len(lote) >= 500:
                        Producto.objects.bulk_create(lote)
                        creados_prod += len(lote)
                        self.stdout.write(f'  ...{creados_prod} productos insertados')
                        lote = []

                multiplicador += 1

            # Insertar el lote final
            if lote:
                Producto.objects.bulk_create(lote)
                creados_prod += len(lote)

        total = Producto.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'\nListo. Categorias creadas: {creados_cat} | '
            f'Productos creados: {creados_prod} | '
            f'Omitidos (ya existian): {omitidos} | '
            f'Total en BD: {total}'
        ))
