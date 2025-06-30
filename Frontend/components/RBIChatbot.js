import React, { useState, useRef, useEffect } from 'react';
import './RBIChatbot.css';

function RBIChatbot() {
  const [isOpen, setIsOpen] = useState(false);
  const [inputMessage, setInputMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const BASE_URL = "http://localhost:8000";

  function toggleChat() {
    setIsOpen(!isOpen);
  }

  function scrollToBottom() {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }

  useEffect(function () {
    scrollToBottom();
  }, [messages]);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!inputMessage.trim()) return;

    const userMessage = { text: inputMessage, sender: 'user' };
    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const policyResponse = await fetch(`${BASE_URL}/api/policy-answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: inputMessage }),
      });

      if (!policyResponse.ok) throw new Error('Failed to get policy answer');
      const policyData = await policyResponse.json();
      setMessages(prev => [...prev, { text: policyData.answer, sender: 'bot', type: 'policy' }]);

      setMessages(prev => [...prev, { text: "Searching web for additional information...", sender: 'bot', type: 'status' }]);
      const webResponse = await fetch(`${BASE_URL}/api/web-answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: inputMessage }),
      });

      if (!webResponse.ok) throw new Error('Failed to get web answer');
      const webData = await webResponse.json();
      setMessages(prev => {
        const newMessages = [...prev];
        if (newMessages[newMessages.length - 1]?.type === 'status') newMessages.pop();
        return [...newMessages, { text: webData.answer, sender: 'bot', type: 'web' }];
      });

      setMessages(prev => [...prev, { text: "Checking data sources...", sender: 'bot', type: 'status' }]);
      const dataResponse = await fetch(`${BASE_URL}/api/data-answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: inputMessage }),
      });

      if (!dataResponse.ok) throw new Error('Failed to get data answer');
      const dataData = await dataResponse.json();
      setMessages(prev => {
        const newMessages = [...prev];
        if (newMessages[newMessages.length - 1]?.type === 'status') newMessages.pop();
        return [...newMessages, { text: dataData.answer, sender: 'bot', type: 'data' }];
      });

    } catch (error) {
      setMessages(prev => {
        const newMessages = [...prev];
        if (newMessages[newMessages.length - 1]?.type === 'status') newMessages.pop();
        return [...newMessages, { text: "Sorry, the server is busy. Try after some time", sender: 'bot', type: 'error' }];
      });
    } finally {
      setIsLoading(false);
    }
  }

  function renderMessageContent(text, type) {
    return text.split('\n').map((paragraph, i) => {
      if (type === 'web' && paragraph.startsWith('  URL: ')) {
        const url = paragraph.replace('  URL: ', '').trim();
        return (
          <p key={i} className="message-content">
            <a href={url} target="_blank" rel="noopener noreferrer" className="web-link">
              {url}
            </a>
          </p>
        );
      }
      return <p key={i} className="message-content">{paragraph}</p>;
    });
  }

  return (
    <div className={'chatbot-container ' + (isOpen ? 'open' : '')}>
      {isOpen ? (
        <div className="chatbot-window">
          <div className="chatbot-header">
            <h3>Bank Audit Assistant</h3>
            <button className="close-btn" onClick={toggleChat}>×</button>
          </div>

<div className="chatbot-messages">
  {messages.length === 0 ? (
    <div className="welcome-message">
      <p>Welcome! Ask me anything about Bank Audit (Testing Model)</p>
      <p>I'll provide answers from RBI documents, web sources, and Guidance Note on Audit of Banks 
        (2025 Edition). <br/><i> For queries contact email info@databoltahi.com</i>.</p>
    </div>
  ) : (
    (() => {
      const renderedMessages = [];
      let i = 0;
      while (i < messages.length) {
        const current = messages[i];
        const next1 = messages[i + 1];
        const next2 = messages[i + 2];

        const isBotGroup = (
          current.sender === 'bot' &&
          next1?.sender === 'bot' &&
          next2?.sender === 'bot' &&
          ['policy', 'web', 'data'].includes(current.type) &&
          ['policy', 'web', 'data'].includes(next1.type) &&
          ['policy', 'web', 'data'].includes(next2.type)
        );

        if (isBotGroup) {
          const group = [current, next1, next2];
          const sortedGroup = ['policy', 'web', 'data'].map(type => group.find(msg => msg.type === type));
          renderedMessages.push(
            <div key={i} className="message-row">
              {sortedGroup.map((msg, index) => (
                <div key={index} className={`message bot`} data-type={msg.type}>
                  {renderMessageContent(msg.text, msg.type)}
                </div>
              ))}
            </div>
          );
          i += 3;
        } else {
          renderedMessages.push(
            <div key={i} className={`message ${current.sender}`} data-type={current.type}>
              {renderMessageContent(current.text, current.type)}
            </div>
          );
          i++;
        }
      }
      return renderedMessages;
    })()
  )}
  <div ref={messagesEndRef} />
</div>


          <form onSubmit={handleSubmit} className="chatbot-input">
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder="Ask about RBI guidelines..."
              disabled={isLoading}
            />
            <button type="submit" disabled={isLoading}>
              {isLoading ? (
                <span className="loading-dots">
                  <span>.</span><span>.</span><span>.</span>
                </span>
              ) : 'Send'}
            </button>
          </form>
        </div>
      ) : (
        <button className="chatbot-button" onClick={toggleChat}>
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          Bank Audit Assistant
        </button>
      )}
    </div>
  );
}

export default RBIChatbot;