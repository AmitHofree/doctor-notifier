export default {
	async fetch(request, env) {
	  if (request.method === 'POST') {
		const requestBody = await request.json();
		const message = requestBody.message;
		
		if (!message || !message.text || !message.chat || !message.chat.id) {
		  console.log("Invalid request: Missing message, text, or chat information");
		  return new Response('Invalid request', { status: 400 });
		}
		
		const chatId = message.chat.id.toString();
		const text = message.text.toLowerCase();
		console.log(`Received command: ${text} from chat ID: ${chatId}`);
		
		if (text === '/register') {
		  const responseMessage = await registerUser(chatId, env);
		  console.log(`Register user response: ${responseMessage}`);
		  return sendMessage(chatId, responseMessage, env);
		} else if (text === '/unregister') {
		  const responseMessage = await unregisterUser(chatId, env);
		  console.log(`Unregister user response: ${responseMessage}`);
		  return sendMessage(chatId, responseMessage, env);
		} else {
		  // Handle other commands or messages as needed
		  console.log("Sending welcome message");
		  return sendMessage(chatId, "Welcome to the Doctor Appointment Notification Bot. Use /register to subscribe or /unregister to unsubscribe from notifications.", env);
		}
	  }
	  
	  console.log("Method not allowed: Only POST method is supported");
	  return new Response('Method Not Allowed', { status: 405 });
	},
  };
  
  async function registerUser(chatId, env) {
	const activeChatIds = await getActiveChatIds(env);
	if (!activeChatIds.includes(chatId)) {
	  activeChatIds.push(chatId);
	  await saveActiveChatIds(activeChatIds, env);
	  return "You are now registered for updates.";
	} else {
	  return "You are already registered for updates!";
	}
  }
  
  async function unregisterUser(chatId, env) {
	const activeChatIds = await getActiveChatIds(env);
	const index = activeChatIds.indexOf(chatId);
	if (index > -1) {
	  activeChatIds.splice(index, 1);
	  await saveActiveChatIds(activeChatIds, env);
	  return "You are now unregistered from updates.";
	} else {
	  return "You are not registered for updates.";
	}
  }
  
  async function getActiveChatIds(env) {
	const data = await env.STORAGE.get("active_chat_ids");
	return data ? JSON.parse(data) : [];
  }
  
  async function saveActiveChatIds(chatIds, env) {
	await env.STORAGE.put("active_chat_ids", JSON.stringify(chatIds));
  }
  
  async function sendMessage(chatId, text, env) {
	const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
	  method: 'POST',
	  headers: { 'Content-Type': 'application/json' },
	  body: JSON.stringify({
		chat_id: chatId,
		text: text,
	  }),
	});
	return new Response(JSON.stringify(await response.json()), { status: 200, headers: { 'Content-Type': 'application/json' } });
  }
  