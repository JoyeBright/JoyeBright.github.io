---
title: Contact
layout: collection
permalink: /contact/
entries_layout: grid
classes: wide
excerpt: This page is a way to be keep in touch with Javad PourMostafa.
---
<form id="fs-frm" name="simple-contact-form" accept-charset="utf-8" action="https://formspree.io/javad.pourmostafa@gmail.com" method="post">
  <fieldset id="fs-frm-inputs">
    <label for="full-name">Full Name</label>
    <input type="text" name="name" id="full-name" placeholder="First and Last" required="">
    <label for="email-address">Email Address</label>
    <input type="email" name="_replyto" id="email-address" placeholder="email@domain" required="">
    <label for="message">Message</label>
    <textarea rows="5" name="message" id="message" placeholder="" required=""></textarea>
    <input type="hidden" name="_subject" id="email-subject" value="Contact Form Submission">
  </fieldset>
  <input type="submit" value="Submit">
</form>
