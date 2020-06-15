---
title: Blog
layout: single
permalink: /blog/
author_profile: true
excerpt: This page indicates all posts connected to Javad PourMostafa's blog.
---

<ul>
  {% for post in site.posts %}
    <li>
      <a href="{{ post.url }}">{{ post.title }}</a>
      {{ post.excerpt }}
    </li>
  {% endfor %}
</ul>

