---
title: Blog
layout: single
permalink: /blog/
author_profile: true
excerpt: This page indicates all posts concerning with computer science and with the major interests in artificial intelligence.
---

<ul>
  {% for post in site.posts %}
    <li>
      <a href="{{ post.url }}">{{ post.title }}</a>
      {{ post.excerpt }}
    </li>
  {% endfor %}
</ul>

