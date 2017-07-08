from django.conf.urls import url, include
from myApi import views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.contrib import admin

urlpatterns = [
    url(r'^$', views.home_page, name='home_page'),
    url(r'^project$', views.ProjectIndexView.as_view(), name='project_index'),
    url(r'^statistics_algo$', views.statistics_algo, name='statistics_algo'),
    url(r'^single_use_rate$', views.single_use_rate, name='single_use_rate'),

    url(r'^product_use_rate_get_detail', views.product_use_rate_get_detail, name='product_use_rate_get_detail'),
    url(r'^single_use_rate_demo$', views.single_use_rate_demo, name='single_use_rate_demo'),
    url(r'^product_use_rate_demo$', views.product_use_rate_demo, name='product_use_rate_demo'),
    url(r'^product/(?P<p_id>\d+)/$', views.cut_detail, name='cut_detail'),
    url(r'^project_detail/(?P<p_id>\d+)/$', views.project_detail, name='project_detail'),
    url(r'^best_piece/$', views.best_piece, name='best_piece'),
    # url(r'^save_work/$', views.save_work, name='save_work'),
    url(r'^save_work/$', views.find_best_piece_job, name='find_best_piece_job'),
    # url(r'^save_work_all/$', views.save_work_all, name='save_work_all'),
    url(r'^calc_comment', views.statical_comment, name='statical_comment'),
    url(r'^nlp_learn/$', views.learn_classify_comment, name='nlp_learn'),
    url(r'^upload_file/$', views.upload_file, name='upload_file'),
    url(r'^predict_sentence/$', views.predict_sentence, name='predict_sentence'),
    url(r'^get_comment_sentence$', views.get_comment_sentence, name='get_comment_sentence'),
    url(r'^get_all_comment', views.get_all_comment, name='get_all_comment'),
    url(r'^get_comment_and_pic', views.get_comment_and_pic, name='get_comment_and_pic'),
    url(r'^single_use_rate_job/$', views.single_use_rate_job, name='single_use_rate_job'),

    # url(r'^product_use_rate$', views.product_use_rate, name='product_use_rate'),
    url(r'^product_use_rate$', views.product_use_rate_job, name='product_use_rate_job'),
    url(r'^admin/', include(admin.site.urls)),
]
urlpatterns += staticfiles_urlpatterns()
