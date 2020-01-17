---
title: Blog
layout: posts
permalink: /blog/
entries_layout: grid
classes: wide
excerpt: This page indicates all posts concerning with computer science and with the major interests in artificial intelligence.
---

{% for category in site.categories %}
  <h3>{{ category[0] }}</h3>
  <ul>
    {% for post in category[1] %}
      <li><a href="{{ post.url }}">{{ post.title }}</a></li>
    {% endfor %}
  </ul>
{% endfor %}
