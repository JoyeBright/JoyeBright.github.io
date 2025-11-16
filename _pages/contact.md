---
title: Contact
layout: collection
permalink: /contact/
entries_layout: grid
classes: wide
---

<form id="fs-frm" name="simple-contact-form" accept-charset="utf-8" action="https://formspree.io/javad.pourmostafa@gmail.com" method="post">
  <fieldset id="fs-frm-inputs">
    <legend>Get in Touch</legend>
    
    <label for="full-name">Full Name</label>
    <input type="text" name="name" id="full-name" placeholder="John Doe" required="">
    
    <label for="email-address">Email Address</label>
    <input type="email" name="_replyto" id="email-address" placeholder="email@host.domain" required="">
    
    <label for="message">Message</label>
    <textarea rows="5" name="message" id="message" placeholder="Write your message here..." required=""></textarea>
    
    <input type="hidden" name="_subject" id="email-subject" value="Contact Form Submission">
  </fieldset>
  
  <input type="submit" value="Send Message" class="submit-button">
</form>

<style>
  #fs-frm {
    max-width: 600px;
    margin: auto;
    padding: 20px;
    border: 1px solid #ddd;
    border-radius: 5px;
    background: #f9f9f9;
  }

  label {
    display: block;
    margin-bottom: 5px;
    font-weight: bold;
  }

  input[type="text"],
  input[type="email"],
  textarea {
    width: 100%;
    padding: 10px;
    margin-bottom: 15px;
    border: 1px solid #ccc;
    border-radius: 4px;
  }

  input[type="submit"] {
    background-color: #4CAF50;
    color: white;
    border: none;
    padding: 10px 15px;
    border-radius: 5px;
    cursor: pointer;
  }

  input[type="submit"]:hover {
    background-color: #45a049;
  }

  legend {
    font-size: 1.5em;
    margin-bottom: 15px;
    text-align: center;
  }
</style>
