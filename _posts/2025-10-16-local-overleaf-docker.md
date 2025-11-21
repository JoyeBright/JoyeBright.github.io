---
classes: wide
title:  "Guide to Using Overleaf Locally"
categories:
  - Misc
tags:
  - Overleaf
  - Local_Overleaf
  - Overlead_docker
---

### You can also view this post on Notion at [HERE](https://j-pourmostafa.notion.site/guide-to-using-overleaf-locally)

## ℹ️ About this guide

This guide walks you through installing and running **Overleaf Community Edition (CE)** entirely **offline** on your own computer — with all major LaTeX packages pre-installed and ready to use.

Since Overleaf recently restricted free compilation times, many students struggle to complete their theses or projects. This guide helps you set up a fully functional local Overleaf, so you can compile your work without limitations.

> ☠️ Let op: Always back up your projects on disk — deleted projects cannot be recovered.
> 

---

## 🐋 Install Docker

> 💡 You only need to do this once.
> 
1. Go to [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
2. Download **Docker Desktop** for your OS (Windows / macOS / Linux).
3. Install and start Docker Desktop.
4. Verify installation by running:
    
```bash
docker --version
```
    

---

## 🚀 Run Overleaf Locally

1️⃣ **Clone the repository**

```bash
git clone https://github.com/JoyeBright/overleaf-docker.git
cd overleaf-docker
```

2️⃣ **Make the launcher executable**

> Run this once to fix permissions:
> 

```bash
chmod +x start-overleaf.sh
```

3️⃣ **Start Overleaf**

```bash
./start-overleaf.sh
```

4️⃣ **Open your browser**

Go to [http://localhost:8080](http://localhost:8080/)

5️⃣ **Create your admin account (first-time setup)**

Visit [http://localhost:8080/launchpad](http://localhost:8080/launchpad)

➡️ Add a username and password

Then return to [http://localhost:8080](http://localhost:8080/) to log in.

6️⃣ **Welcome Screen**

You’ll see **“Welcome to Overleaf Local”** — click on **“Start Using Overleaf”** to enter the editor.

![Screenshot 2025-11-11 at 06.06.43.png](https://javad.pourmostafa.com/assets/images/Screenshot_2025-11-11_at_06.06.43.png)

6️⃣ **Import or Create Your Thesis Project**

Once logged in:

- Click **“Create a new project → Upload Project”** to import your `.zip` or `.tex` project. Example: [DSS Thesis Information](https://tilburguniversity.instructure.com/courses/19187/pages/thesis-template-information?module_item_id=925936) or choose **“**Blank Project**”** to start from scratch.
    
    ![Screenshot 2025-11-11 at 06.07.54.png](https://javad.pourmostafa.com/assets/images/Screenshot_2025-11-11_at_06.07.54.png)
    
    ![Screenshot 2025-11-11 at 06.21.09.png](https://javad.pourmostafa.com/assets/images/Screenshot_2025-11-11_at_06.21.09.png)
    

---

## 📁 Files in This Project

| File | Description |
| --- | --- |
| `docker-compose.yml` | Defines Overleaf, MongoDB, and Redis containers |
| `start-overleaf.sh` | One-click launcher script |

---

## 🧰 Useful Commands

---

| Action | Command | When to use it |
| --- | --- | --- |
| 🛑 Stop Overleaf | `docker stop overleaf` | When you want to temporarily stop the Overleaf container (e.g., for maintenance or updates). |
| 🚀 Start Overleaf | `docker start overleaf` | When you want to restart the previously stopped Overleaf container without rebuilding it. |
| 🔄 Restart Overleaf | `./start-overleaf.sh` | When you want to fully restart Overleaf — this stops and recreates all containers using the configuration in the script. ⚠️ **Be aware that all projects, users, and settings (including your thesis project) will be permanently removed.** |
| 🧹 Remove all Docker data | `docker system prune -a --volumes -f` | ⚠️ Use with extreme caution — this deletes all Docker containers, images, and volumes system-wide, not just Overleaf. Only use if you want a completely clean Docker environment. |

## 💬 Questions & Help

All the necessary LaTeX packages are already installed to work smoothly with your thesis template. However, if you notice that something is missing or you encounter an error, please let us know via a Github issue.

If you run into any issues, please:

- Open an **issue** here: [github.com/JoyeBright/overleaf-docker/issues](https://github.com/JoyeBright/overleaf-docker/issues)

> 💡 Tip: Include your OS (Windows/macOS/Linux) and the error message for faster support.
>
