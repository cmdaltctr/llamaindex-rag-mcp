import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "../api/ApiProvider";
import { useAppendChatTurn, useCreateChat } from "../api/chatMutations";
import { ApiError } from "../api/client";
import type { ChatSummary } from "../api/chats";
import type { AnswerResult } from "../api/documents";
import { chatQuery } from "../api/queries";
import { useRoute } from "../lib/RouteProvider";

export interface Turn {
  id: number;
  collection: string;
  question: string;
  /** The stored answer of a reopened chat. A turn without one asks the server. */
  saved: AnswerResult | null;
}

const TITLE_LIMIT = 60;

const isMissing = (error: unknown) => error instanceof ApiError && error.status === 404;

function titleOf(question: string): string {
  const flat = question.replace(/\s+/g, " ").trim();
  return flat.length <= TITLE_LIMIT ? flat : `${flat.slice(0, TITLE_LIMIT - 1)}…`;
}

/**
 * The transcript of the open chat and its link to the stored chat (ADR-082).
 * The first usable answer creates the chat and puts its id in the route. Each
 * later usable answer is saved as a turn. An error result is never saved. A
 * save that fails does not stop the chat: a 404 means the chat was deleted
 * while the answer was pending and is dropped silently, any other failure
 * shows one line.
 */
export function useChatSession(routeCollection: string | null, routeChatId: string | null) {
  const api = useApi();
  const queryClient = useQueryClient();
  const { navigate } = useRoute();
  const createChat = useCreateChat();
  const appendTurn = useAppendChatTurn();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [session, setSession] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);
  const [chatId, setChatId] = useState<string | null>(null);
  const chatIdRef = useRef<string | null>(null);
  // The newest collection in the route. A save that finishes later must not undo a knowledge base the user picked meanwhile.
  const routeCollectionRef = useRef(routeCollection);
  useEffect(() => {
    routeCollectionRef.current = routeCollection;
  }, [routeCollection]);
  // Bumped whenever the screen shows another chat, so a save that finishes later can tell the screen has moved on.
  const sessionRef = useRef(0);
  const creating = useRef<{ session: number; promise: Promise<string | null> } | null>(null);
  // Saves run one after another, so turns reach the server in the order the answers arrived.
  const saving = useRef<Promise<void>>(Promise.resolve());

  const advanceSession = useCallback(() => {
    sessionRef.current += 1;
    creating.current = null;
    setSession(sessionRef.current);
  }, []);

  const adopt = useCallback((id: string | null) => {
    chatIdRef.current = id;
    setChatId(id);
  }, []);

  // Opening a chat id that is not the one on screen loads it from the server.
  useEffect(() => {
    if (routeChatId === null || routeChatId === chatIdRef.current) return;
    let cancelled = false;
    queryClient
      .fetchQuery({ ...chatQuery(api, routeChatId), staleTime: 0 })
      .then((chat) => {
        if (cancelled) return;
        adopt(chat.chat_id);
        setNotice(null);
        advanceSession();
        setTurns(chat.turns.map((t, index) => ({ id: index + 1, collection: t.collection, question: t.question, saved: t.answer })));
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        // Only a 404 means the chat is gone. Any other failure keeps the route so the user can try again.
        if (!isMissing(error)) {
          setNotice("This chat could not be loaded. Reload the page to try again.");
          return;
        }
        adopt(null);
        setTurns([]);
        advanceSession();
        setNotice("That chat is no longer stored. You can start a new one.");
        navigate({ area: "chat", collection: routeCollection, chatId: null }, { replace: true });
      });
    return () => {
      cancelled = true;
    };
  }, [routeChatId, routeCollection, api, queryClient, adopt, advanceSession, navigate]);

  /** Opens a stored chat in the collection of its last turn (design D7). */
  const openChat = useCallback(
    async (chat: ChatSummary) => {
      if (chat.chat_id === chatIdRef.current) return;
      try {
        const detail = await queryClient.fetchQuery(chatQuery(api, chat.chat_id));
        const collection = detail.turns.at(-1)?.collection ?? routeCollection;
        navigate({ area: "chat", collection, chatId: chat.chat_id });
      } catch (error) {
        setNotice(isMissing(error) ? "That chat is no longer stored. You can start a new one." : "This chat could not be loaded. Try again.");
      }
    },
    [api, queryClient, navigate, routeCollection],
  );

  const send = useCallback(
    (collection: string) => (question: string) =>
      setTurns((current) => [...current, { id: (current.at(-1)?.id ?? 0) + 1, collection, question, saved: null }]),
    [],
  );

  const newChat = useCallback(() => {
    adopt(null);
    setTurns([]);
    setNotice(null);
    advanceSession();
    navigate({ area: "chat", collection: routeCollection, chatId: null }, { replace: true });
  }, [adopt, advanceSession, navigate, routeCollection]);

  const ensureChat = useCallback(
    (turn: Turn, expected: number): Promise<string | null> => {
      if (expected === sessionRef.current && chatIdRef.current !== null) return Promise.resolve(chatIdRef.current);
      if (creating.current?.session === expected) return creating.current.promise;
      const promise = createChat
        .mutateAsync({ title: titleOf(turn.question) })
        .then((chat) => {
          // The answer is stored in the chat just made. The screen only follows it while it still shows that session.
          if (expected === sessionRef.current) {
            adopt(chat.chat_id);
            navigate({ area: "chat", collection: routeCollectionRef.current ?? turn.collection, chatId: chat.chat_id }, { replace: true });
          }
          return chat.chat_id;
        })
        .catch(() => {
          setNotice("This answer could not be saved to the chat history.");
          return null;
        })
        .finally(() => {
          if (creating.current?.promise === promise) creating.current = null;
        });
      creating.current = { session: expected, promise };
      return promise;
    },
    [adopt, createChat, navigate],
  );

  const onResult = useCallback(
    (turn: Turn, result: AnswerResult) => {
      if (result.status === "error") return Promise.resolve();
      const expected = sessionRef.current;
      const save = saving.current.then(async () => {
        const id = await ensureChat(turn, expected);
        if (id === null) return;
        try {
          await appendTurn.mutateAsync({ chatId: id, turn: { collection: turn.collection, question: turn.question, answer: result } });
        } catch (error) {
          if (!isMissing(error)) setNotice("This answer could not be saved to the chat history.");
        }
      });
      saving.current = save.catch(() => undefined);
      return save;
    },
    [appendTurn, ensureChat],
  );

  return { turns, session, notice, chatId, send, newChat, openChat, onResult };
}
