import { QueryClient } from "@tanstack/react-query";
import { restorePersisted, startPersisting } from "./persist";

// gcTime 24시간: 다른 화면에 갔다 와도 받은 데이터를 버리지 않고 바로 보여줌 (뒤에서 최신 데이터로 갱신)
export const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, gcTime: 24 * 60 * 60 * 1000 } },
});

restorePersisted(queryClient);
startPersisting(queryClient);
