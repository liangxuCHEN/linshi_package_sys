from django.db import models


class Userate(models.Model):
    name = models.CharField(max_length=256)
    rate = models.FloatField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('created',)


class ProductRateDetail(models.Model):
    sheet_name = models.CharField(max_length=512)
    num_sheet = models.IntegerField()
    avg_rate = models.FloatField()
    rates = models.TextField()
    detail = models.TextField()
    num_shape = models.CharField(max_length=1000)
    sheet_num_shape = models.CharField(max_length=2000)
    pic_url = models.CharField(max_length=1024, null=True)
    same_bin_list = models.CharField(max_length=2000, null=True)
    empty_sections = models.TextField(null=True)
    algorithm = models.IntegerField(null=True)
    empty_section_ares = models.CharField(max_length=3500, null=True)
    total_rates = models.TextField(null=True)


class Project(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    products = models.ManyToManyField(ProductRateDetail)
    data_input = models.TextField(null=True)
    comment = models.TextField()

    class Meta:
        ordering = ('created',)
