---
title: Blog
layout: single
permalink: /blog/
author_profile: true
excerpt: Notes on NLP, deep learning, and selected topics in computer science.
---

<p class="page-intro">
  Writing about NLP, deep learning, and practical computer science.
</p>

<ul class="post-list">
  {% for post in site.posts %}
    <li class="post-item">
      <h2 class="post-title">
        <a href="{{ post.url | relative_url }}">
          {{ post.title }}
        </a>
      </h2>

      <span class="post-meta">
        {{ post.date | date: "%B %d, %Y" }}
      </span>

      <p class="post-excerpt">
        {{ post.excerpt | strip_html | truncate: 160 }}
      </p>
    </li>
  {% endfor %}
</ul>
