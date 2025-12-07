import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { MessageBox } from "../components/MessageBox";
import "../style/dcf-npm.css";

const meta = {
  title: "Buckaroo/MessageBox",
  component: MessageBox,
  parameters: {
    layout: "padded",
  },
  tags: ["autodocs"],
  argTypes: {
    messages: {
      control: "object",
      description: "Array of message objects to display",
    },
  },
} satisfies Meta<typeof MessageBox>;

export default meta;
type Story = StoryObj<typeof meta>;

// Sample cache messages
const cacheMessages = [
  {
    time: "2024-01-15T10:00:00.000Z",
    type: "cache",
    message: "file found in cache with file name /path/to/data.parquet",
  },
  {
    time: "2024-01-15T10:00:01.000Z",
    type: "cache",
    message: "file not found in cache for file name /path/to/new_data.parquet",
  },
];

// Sample cache info message
const cacheInfoMessages = [
  {
    time: "2024-01-15T10:00:02.000Z",
    type: "cache_info",
    message: "Cache info. 30 columns in cache, 14 stats per column, total cache size 3.2 kilobytes",
  },
];

// Sample execution update messages
const executionMessages = [
  {
    time: "2024-01-15T10:00:03.000Z",
    type: "execution",
    message: "Execution update: started",
    time_start: "2024-01-15T10:00:03.000Z",
    pid: 12345,
    status: "started",
    num_columns: 5,
    num_expressions: 12,
    explicit_column_list: ["col1", "col2", "col3", "col4", "col5"],
  },
  {
    time: "2024-01-15T10:00:05.500Z",
    type: "execution",
    message: "Execution update: finished",
    time_start: "2024-01-15T10:00:03.000Z",
    pid: 12345,
    status: "finished",
    num_columns: 5,
    num_expressions: 12,
    explicit_column_list: ["col1", "col2", "col3", "col4", "col5"],
    execution_time_secs: 2.5,
  },
  {
    time: "2024-01-15T10:00:08.000Z",
    type: "execution",
    message: "Execution update: error",
    time_start: "2024-01-15T10:00:08.000Z",
    pid: 12346,
    status: "error",
    num_columns: 2,
    num_expressions: 8,
    explicit_column_list: ["col6", "col7"],
  },
];

// Mixed messages showing typical workflow
const mixedMessages = [
  ...cacheMessages,
  ...cacheInfoMessages,
  ...executionMessages,
];

export const Empty: Story = {
  args: {
    messages: [],
  },
};

export const CacheMessages: Story = {
  args: {
    messages: cacheMessages,
  },
};

export const CacheInfo: Story = {
  args: {
    messages: cacheInfoMessages,
  },
};

export const ExecutionUpdates: Story = {
  args: {
    messages: executionMessages,
  },
};

export const MixedMessages: Story = {
  args: {
    messages: mixedMessages,
  },
};

export const ManyMessages: Story = {
  args: {
    messages: Array.from({ length: 50 }, (_, i) => ({
      time: `2024-01-15T10:00:${String(i).padStart(2, "0")}.000Z`,
      type: i % 3 === 0 ? "cache" : i % 3 === 1 ? "cache_info" : "execution",
      message: `Message ${i + 1}: ${i % 3 === 0 ? "Cache operation" : i % 3 === 1 ? "Cache info update" : "Execution update"}`,
      ...(i % 3 === 2
        ? {
            time_start: `2024-01-15T10:00:${String(i).padStart(2, "0")}.000Z`,
            pid: 12345 + i,
            status: i % 5 === 0 ? "error" : "finished",
            num_columns: (i % 10) + 1,
            num_expressions: (i % 20) + 5,
            explicit_column_list: Array.from({ length: (i % 10) + 1 }, (_, j) => `col${j + 1}`),
            execution_time_secs: (i % 10) * 0.5,
          }
        : {}),
    })),
  },
};

export const LongMessages: Story = {
  args: {
    messages: [
      {
        time: "2024-01-15T10:00:00.000Z",
        type: "cache",
        message: "file found in cache with file name /very/long/path/to/a/very/large/dataset/with/many/subdirectories/data.parquet",
      },
      {
        time: "2024-01-15T10:00:01.000Z",
        type: "execution",
        message: "Execution update: finished",
        time_start: "2024-01-15T10:00:00.000Z",
        pid: 12345,
        status: "finished",
        num_columns: 150,
        num_expressions: 300,
        explicit_column_list: Array.from({ length: 150 }, (_, i) => `very_long_column_name_${i}_with_many_characters`),
        execution_time_secs: 123.456,
      },
    ],
  },
};

// Streaming messages story - simulates messages being added over time
export const StreamingMessages: Story = {
  render: (args) => {
    const [messages, setMessages] = useState<typeof args.messages>([]);
    const [isStreaming, setIsStreaming] = useState(false);
    
    const startStreaming = () => {
      setIsStreaming(true);
      setMessages([]);
      
      // Simulate cache messages
      setTimeout(() => {
        setMessages(prev => [...prev, {
          time: new Date().toISOString(),
          type: "cache",
          message: "file not found in cache for file name /path/to/data.parquet",
        }]);
      }, 500);
      
      setTimeout(() => {
        setMessages(prev => [...prev, {
          time: new Date().toISOString(),
          type: "cache_info",
          message: "Cache info. 30 columns in cache, 14 stats per column, total cache size 3.2 kilobytes",
        }]);
      }, 1000);
      
      // Simulate execution updates
      let execCount = 0;
      const addExecutionUpdate = () => {
        execCount++;
        const colGroup = Array.from({ length: 3 }, (_, i) => `col${execCount * 3 + i}`);
        const status = execCount % 3 === 0 ? "error" : execCount % 2 === 0 ? "finished" : "started";
        
        setMessages(prev => [...prev, {
          time: new Date().toISOString(),
          type: "execution",
          message: `Execution update: ${status}`,
          time_start: new Date().toISOString(),
          pid: 12345 + execCount,
          status: status,
          num_columns: colGroup.length,
          num_expressions: 12,
          explicit_column_list: colGroup,
          ...(status === "finished" ? { execution_time_secs: 1.5 + Math.random() } : {}),
        }]);
        
        if (execCount < 10) {
          setTimeout(addExecutionUpdate, 1500);
        } else {
          setIsStreaming(false);
        }
      };
      
      setTimeout(addExecutionUpdate, 2000);
    };
    
    return (
      <div>
        <div style={{ marginBottom: "10px" }}>
          <button 
            onClick={startStreaming} 
            disabled={isStreaming}
            style={{ padding: "8px 16px", marginRight: "10px" }}
          >
            {isStreaming ? "Streaming..." : "Start Streaming Messages"}
          </button>
          {messages.length > 0 && (
            <span style={{ marginLeft: "10px" }}>
              {messages.length} message{messages.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <MessageBox messages={messages} />
      </div>
    );
  },
  args: {
    messages: [],
  },
};

