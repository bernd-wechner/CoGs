from django.urls import path

from . import views

app_name = 'Import'

urlpatterns = [
    path('', views.view_Import.as_view(model="Import"), name='index'),
    path('map', views.view_Map, name='map')
]
