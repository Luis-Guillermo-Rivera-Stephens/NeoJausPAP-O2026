import httpx

if __name__ == "__main__":
    chat_id = None
    while True:
        mensaje = input("Ingrese un mensaje: ")
        if mensaje.lower() == "exit":
            break
        payload = {"message": mensaje}
        if chat_id:
            payload["chat_id"] = chat_id
        response = httpx.post("http://127.0.0.1:8000/chat", json=payload, timeout=120.0)
        response.raise_for_status()
        data = response.json()
        chat_id = data["chat_id"]
        print(data["reply"])
