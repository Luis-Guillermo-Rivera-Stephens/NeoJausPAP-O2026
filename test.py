import httpx

if __name__ == "__main__":
    while True:
        mensaje = input("Ingrese un mensaje: ")
        if mensaje.lower() == "exit":
            break
        response = httpx.post(
            "http://127.0.0.1:8000/chat",
            json={"message": mensaje},
            timeout=120.0,
        )
        response.raise_for_status()
        print(response.json()["reply"])
