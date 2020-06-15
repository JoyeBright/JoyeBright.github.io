---
title: Blog
layout: single
permalink: /blog/
author_profile: true
excerpt: This page comprises of posts connected to Javad PourMostafa's blog. They lie primarily in NLP and Deep Neural Networks. However, some other subjects related to computer science will be published here.
---

<ul>
  {% for post in site.posts %}
    <li>
      <a href="{{ post.url }}">{{ post.title }}</a>
      {{ post.excerpt }}
    </li>
  {% endfor %}
</ul>

